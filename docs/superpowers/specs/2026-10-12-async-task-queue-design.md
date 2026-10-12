---
comet_change: async-task-queue
role: technical-design
canonical_spec: openspec
---

# 异步任务队列系统 - 技术设计

## 概述

本设计实现异步任务队列系统，将长时间运行的评估任务从 API 请求中解耦，通过 Celery + Redis 提供非阻塞的任务提交、状态查询和管理功能。

**核心目标**：
- 解决评估任务（数分钟到数小时）导致的 HTTP 超时问题
- 提供任务状态查询、暂停/恢复/取消功能
- 保持与现有 TaskService 和 `--resume` 功能的兼容性
- 为未来扩展到 experiment/import/benchmark 提供统一框架

**实现范围**（Phase 1）：
- 只实现 evaluation 异步化
- Experiment/Import/Benchmark 保持 CLI only（延后）

---

## 架构设计

### 整体架构

```
客户端
  ↓ POST /evaluations
API 层（FastAPI）
  ↓ EvaluationService.create_evaluation()
服务层（TaskManager）
  ↓ create_task() → 提交 Celery 任务
任务层（Celery Worker）
  ↓ run_evaluation_task() → TaskService.run()
执行层（TaskService）
  ↓ 评估执行器
数据层
  ├─ async_tasks 表（任务状态）
  ├─ evaluations 表（业务记录）
  └─ TaskService JSON（详细单元状态）
```

### 架构层次

**API 层**：
- 改造现有 `/api/v1/evaluations` 端点
- `POST /evaluations` 立即返回（< 1 秒），状态为 `pending`
- `GET /evaluations/{id}` 聚合实时状态和进度
- 新增 `POST /evaluations/{id}/pause`、`POST /evaluations/{id}/resume`

**服务层（TaskManager）**：
- 统一的任务生命周期管理抽象
- 负责 AsyncTask CRUD 和 Celery 任务提交
- 聚合 Celery 实时状态和数据库记录
- 支持未来扩展到其他任务类型

**任务层（Celery）**：
- `run_evaluation_task` 封装 TaskService 调用
- 通过回调实时同步进度到数据库
- 混合重试策略（基础设施错误自动重试，业务错误不重试）

**执行层（TaskService）**：
- 复用现有的任务编排能力
- 提供单元级恢复、pause/resume 机制
- JSON 文件持久化详细状态

---

## 数据模型设计

### 新增 `async_tasks` 表

通用的异步任务状态管理表，与具体业务实体解耦。

**字段设计**：

```python
class AsyncTask(Base):
    __tablename__ = "async_tasks"
    
    # 主键和关联
    id: str                      # UUID，主键
    celery_task_id: str | None   # Celery 任务 ID（唯一索引）
    
    # 任务分类
    task_type: str               # "evaluation", "experiment", "import", "benchmark"
    entity_id: str               # 关联的业务实体 ID（evaluation_id 等）
    user_id: str                 # 用户标识（索引）
    
    # 状态管理
    status: str                  # pending/running/paused/completed/failed/cancelled
    progress: dict | None        # {"current": 10, "total": 100, "message": "..."}
    error_message: str | None    # 失败原因
    
    # 时间戳
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime
```

**索引**：
- `celery_task_id`（唯一）
- `task_type`
- `entity_id`
- `user_id`
- `status`

### 修改 `evaluations` 表

增加外键关联 `async_tasks` 表。

```python
class Evaluation(Base):
    # ... 现有字段 ...
    
    # 新增字段
    async_task_id: str | None = ForeignKey("async_tasks.id", ondelete="SET NULL")
```

### 状态转换

```
pending → running → completed
              ↓
              ├→ failed
              ├→ cancelled
              └→ paused → running (resume)
```

**状态说明**：
- `pending`：等待 Celery worker 执行
- `running`：正在执行
- `paused`：用户暂停，单元边界优雅停止
- `completed`：所有单元完成（可能部分失败）
- `failed`：任务级错误（配置错误、资源不存在）
- `cancelled`：用户取消，不可恢复

---

## Celery 基础设施

### Celery 配置

**核心配置**（`src/celery_app.py`）：

```python
celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,           # Redis
    result_backend=settings.CELERY_RESULT_BACKEND,   # Redis
    result_expires=7 * 24 * 3600,                    # 结果 7 天过期
    
    # 任务序列化
    task_serializer="json",
    accept_content=["json"],
    
    # Worker 配置
    worker_prefetch_multiplier=1,      # 避免长任务阻塞
    worker_max_tasks_per_child=50,     # 防止内存泄漏
    
    # 任务路由
    task_routes={
        "src.tasks.evaluation.*": {"queue": "evaluations"},
    },
    
    # 重试配置
    task_acks_late=True,                # 完成后才 ack
    task_reject_on_worker_lost=True,    # worker 丢失时重新入队
)
```

### 依赖项

```
celery[redis]>=5.3.0
redis>=5.0.0
```

### 启动方式

```bash
# Worker
celery -A src.celery_app worker \
    --loglevel=info \
    --concurrency=4 \
    --queues=evaluations,default

# Flower 监控（可选）
celery -A src.celery_app flower --port=5555
```

---

## 核心组件设计

### TaskManager（`src/task_manager.py`）

统一的任务管理抽象层，提供以下能力：

**方法**：
- `create_task()` - 创建 AsyncTask 并提交 Celery
- `get_task()` - 查询任务状态（聚合 Celery 实时状态）
- `update_task_progress()` - 更新进度（Celery 回调）
- `update_task_status()` - 更新状态
- `pause_task()` - 请求暂停
- `resume_task()` - 恢复任务
- `cancel_task()` - 取消任务
- `list_tasks()` - 列出用户任务

**状态聚合逻辑**：

```python
def get_task(task_id, user_id):
    task = db.query(AsyncTask).filter(...).first()
    
    # 如果任务正在运行，聚合 Celery 实时状态
    if task.celery_task_id and task.status in ["pending", "running"]:
        celery_result = AsyncResult(task.celery_task_id)
        if celery_result.state == "PROGRESS":
            task.progress = celery_result.info  # 实时进度
    
    return task
```

### Celery 任务（`src/tasks/evaluation.py`）

**任务定义**：

```python
@celery_app.task(
    bind=True,
    autoretry_for=(RedisConnectionError, ConnectionError),  # 基础设施错误自动重试
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    acks_late=True,
)
def run_evaluation_task(self, evaluation_id: str):
    # 1. 加载 Evaluation 和 AsyncTask
    # 2. 验证配置（业务错误不重试）
    # 3. 创建 TaskService 任务单元
    # 4. 定义进度回调
    # 5. 定义暂停检查
    # 6. 执行 TaskService.run()
    # 7. 更新最终状态
```

**进度回调**：

```python
def on_unit_finished(record, unit):
    # 更新 AsyncTask 进度
    progress = {
        "current": record.completed_units,
        "total": record.total_units,
        "message": f"Completed {record.completed_units}/{record.total_units}",
    }
    task_manager.update_task_progress(async_task_id, progress)
    
    # 更新 Evaluation 记录
    evaluation.completed_count = record.completed_units
    db.commit()
    
    # 报告到 Celery
    self.update_state(state="PROGRESS", meta=progress)
```

**暂停检查**：

```python
def should_pause(record):
    # 检查用户是否请求暂停
    current_task = db.query(AsyncTask).filter(...).first()
    if current_task.status == "paused":
        return True
    
    # 检查预算
    if evaluation.budget_cap_usd and evaluation.spent_usd >= evaluation.budget_cap_usd:
        return True
    
    return False
```

### EvaluationService 改造

**create_evaluation**：

```python
def create_evaluation(request, user_id):
    # 1. 创建 Evaluation 记录
    evaluation = Evaluation(id=uuid4(), user_id=user_id, status="pending", ...)
    db.add(evaluation)
    db.flush()
    
    # 2. 创建 AsyncTask 并提交 Celery
    async_task = task_manager.create_task(
        task_type="evaluation",
        entity_id=evaluation.id,
        user_id=user_id,
        celery_task_name="src.tasks.evaluation.run_evaluation_task",
        celery_task_args=(evaluation.id,),
    )
    
    # 3. 关联 AsyncTask
    evaluation.async_task_id = async_task.id
    db.commit()
    
    return _to_response(evaluation, async_task)
```

**get_evaluation**：

```python
def get_evaluation(evaluation_id, user_id):
    evaluation = db.query(Evaluation).filter(...).first()
    
    # 聚合 AsyncTask 实时状态
    async_task = None
    if evaluation.async_task_id:
        async_task = task_manager.get_task(evaluation.async_task_id)
    
    return _to_response(evaluation, async_task)
```

**pause/resume/delete**：

```python
def pause_evaluation(evaluation_id, user_id):
    evaluation = db.query(Evaluation).filter(...).first()
    async_task = task_manager.pause_task(evaluation.async_task_id, user_id)
    return _to_response(evaluation, async_task)

def resume_evaluation(evaluation_id, user_id):
    # 创建新的 AsyncTask（resume）
    new_task = task_manager.create_task(...)
    evaluation.async_task_id = new_task.id
    db.commit()
    return _to_response(evaluation, new_task)

def delete_evaluation(evaluation_id, user_id):
    # 取消 Celery 任务
    task_manager.cancel_task(evaluation.async_task_id, user_id)
    # 删除 TaskService JSON
    task_service.delete(evaluation.run_id)
    # 删除记录
    db.delete(evaluation)
    db.commit()
```

---

## API 端点设计

### POST /api/v1/evaluations

**行为**：创建评估并提交异步任务，立即返回。

**请求体**：
```json
{
  "strategy_names": ["strategy1", "strategy2"],
  "problem_ids": ["problem1", "problem2"],
  "api_key_id": "key-001",
  "budget_cap_usd": 10.0
}
```

**响应**（status=201）：
```json
{
  "success": true,
  "data": {
    "id": "eval-123",
    "status": "pending",
    "progress": null,
    "created_at": "2025-01-14T10:00:00Z",
    ...
  },
  "message": "Evaluation created and task submitted"
}
```

### GET /api/v1/evaluations/{id}

**行为**：查询评估状态和进度（聚合实时状态）。

**响应**：
```json
{
  "success": true,
  "data": {
    "id": "eval-123",
    "status": "running",
    "progress": {
      "current": 10,
      "total": 100,
      "message": "Completed 10/100 evaluations"
    },
    "completed_count": 10,
    "failed_count": 0,
    ...
  }
}
```

### POST /api/v1/evaluations/{id}/pause

**行为**：请求暂停任务（优雅停止在单元边界）。

**响应**（status=200）：
```json
{
  "success": true,
  "data": { "status": "paused", ... },
  "message": "Evaluation pause requested"
}
```

### POST /api/v1/evaluations/{id}/resume

**行为**：恢复暂停或失败的任务。

**响应**（status=200）：
```json
{
  "success": true,
  "data": { "status": "pending", ... },
  "message": "Evaluation resumed"
}
```

### DELETE /api/v1/evaluations/{id}

**行为**：取消任务并删除所有记录（不可恢复）。

**响应**（status=204）：无内容

---

## 错误处理策略

### 错误分类

**自动重试的错误**（最多 3 次，指数退避）：
- `redis.exceptions.ConnectionError` - Redis 连接失败
- `celery.exceptions.OperationalError` - Celery 操作错误
- 瞬时 LLM API 错误（如 503）

**不重试的错误**（立即标记失败）：
- 配置验证错误（strategy 不存在、problem 不存在）
- 认证错误（API key 无效）
- 资源不存在错误（dataset 文件不存在）
- 预算耗尽

**单元级错误**：
- 由 TaskService 处理，单元失败不影响整体任务
- 整体任务标记为 `completed`（但包含失败单元）
- LLM API 调用失败在单元级处理，不触发任务级重试

### 重试配置

```python
@celery_app.task(
    autoretry_for=(RedisConnectionError, ConnectionError),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,          # 10s, 20s, 40s
    retry_backoff_max=300,       # 最大 5 分钟
)
```

---

## 暂停/恢复机制

### 暂停实现

**优雅停止策略**：
1. 用户调用 `POST /evaluations/{id}/pause`
2. API 更新 `async_task.status = "paused"`
3. Celery 任务通过 `should_pause()` 检测标志
4. 在下一个单元边界优雅退出
5. 正在执行的单元标记为 `uncertain`

**特点**：
- 非立即响应（取决于单元粒度，通常几秒到几分钟）
- 保证数据一致性，避免部分执行的单元
- 未执行的单元保持 `queued` 状态

**暂停检查**：
```python
def should_pause(record):
    # 重新加载 async_task 检查状态
    db.expire_all()
    current_task = db.query(AsyncTask).filter(...).first()
    return current_task.status == "paused"
```

### 恢复实现

**恢复策略**：
1. 用户调用 `POST /evaluations/{id}/resume`
2. API 创建新的 AsyncTask 并提交 Celery
3. Celery 任务调用 `TaskService.run(resume=True)`
4. TaskService 自动跳过已完成单元，重新执行 `uncertain` 单元

**TaskService resume 机制**：
```python
task_service.run(
    run_id,
    worker=worker,
    resume=True,  # 跳过已完成单元
)
```

---

## 任务历史清理策略

### 分层清理

**Celery 结果（Redis）**：
- 自动 TTL = 7 天
- 配置：`result_expires = 7 * 24 * 3600`
- 任务完成后 7 天自动过期

**TaskService JSON 文件**：
- 与数据库记录同步删除
- `DELETE /evaluations/{id}` 时删除对应 JSON 文件
- 可选：定期清理孤儿文件

**数据库记录**：
- 默认永久保留
- 提供 `DELETE /evaluations/{id}` 手动删除
- 可选配置：`AUTO_CLEANUP_ENABLED` 和 `AUTO_CLEANUP_DAYS`

### 清理实现

```python
def delete_evaluation(evaluation_id, user_id):
    evaluation = db.query(Evaluation).filter(...).first()
    
    # 1. 取消 Celery 任务
    if evaluation.async_task_id:
        task_manager.cancel_task(evaluation.async_task_id, user_id)
        db.query(AsyncTask).filter(...).delete()
    
    # 2. 删除 TaskService JSON
    if evaluation.run_id:
        task_service.delete(evaluation.run_id)
    
    # 3. 删除 Evaluation 记录
    db.delete(evaluation)
    db.commit()
```

---

## 测试策略

### 单元测试

**TaskManager**：
- `test_create_task` - 创建任务并提交 Celery
- `test_get_task` - 查询任务和权限检查
- `test_pause_task` - 暂停运行中的任务
- `test_resume_task` - 恢复暂停的任务
- `test_cancel_task` - 取消任务并调用 revoke
- `test_update_task_progress` - 更新进度
- `test_list_tasks` - 列出和过滤任务

**Celery 任务**：
- `test_run_evaluation_task_success` - 成功执行
- `test_run_evaluation_task_not_found` - 评估不存在
- `test_create_task_units` - 单元创建逻辑
- `test_error_retry` - 自动重试机制
- `test_business_error_no_retry` - 业务错误不重试

### 集成测试

**完整流程**：
- `test_create_and_poll_evaluation` - 创建 → 轮询 → 完成
- `test_pause_and_resume_evaluation` - 暂停 → 恢复
- `test_cancel_evaluation` - 取消并删除
- `test_error_handling` - 配置错误、资源不存在

### 覆盖率目标

- ≥ 80%

---

## 部署要求

### 前置条件

1. **Redis 服务**：
   - 版本：≥ 6.0
   - 持久化：建议启用 AOF
   - 配置：`maxmemory-policy allkeys-lru`

2. **数据库迁移**：
   ```bash
   alembic upgrade head
   ```

3. **环境变量**：
   ```bash
   CELERY_BROKER_URL=redis://localhost:6379/0
   CELERY_RESULT_BACKEND=redis://localhost:6379/0
   TASK_SERVICE_ROOT=./data/tasks
   DATABASE_URL=postgresql://user:password@localhost/llm_harness
   ```

### 启动步骤

```bash
# 1. 启动 Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 2. 运行数据库迁移
alembic upgrade head

# 3. 启动 Celery Worker
celery -A src.celery_app worker --loglevel=info --concurrency=4

# 4. 启动 API 服务
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 5. （可选）启动 Flower 监控
celery -A src.celery_app flower --port=5555
```

### 监控指标

- Celery 队列长度（pending 任务数）
- Worker 繁忙率
- 任务失败率
- Redis 内存使用率

### 告警规则

- 队列积压 > 100 个任务
- Worker 失败率 > 5%
- Redis 内存 > 80%

---

## 关键技术取舍

| 决策 | 选择 | 理由 | 代价 |
|------|------|------|------|
| 架构方案 | 方案 2（清晰分层） | 统一抽象，易扩展 | 首次多花 1 周 |
| Worker 并发 | 低并发（1-4） | 避免 LLM API 限流 | 吞吐量受限 |
| 暂停机制 | 优雅停止（单元边界） | 数据一致性 | 非立即响应 |
| 状态存储 | 双层（async_tasks + JSON） | 恢复保障 | 略增复杂度 |
| 结果 TTL | Celery 7 天，DB 永久 | 平衡资源和可追溯性 | 需手动清理 |

---

## 风险与缓解

### 高风险

**TaskService 与 Celery 状态不一致**：
- **缓解**：通过 `on_unit_finished` 回调实时同步
- **监控**：定期检查 async_tasks.status 与 TaskService JSON 的一致性

**Celery Worker 崩溃导致任务丢失**：
- **缓解**：`task_acks_late=True`，任务完成后才 ack
- **恢复**：用户通过 resume 恢复

### 中风险

**Redis 内存溢出**：
- **缓解**：7 天 TTL，`maxmemory-policy allkeys-lru`
- **监控**：Redis 内存使用率告警

**长时间任务阻塞队列**：
- **缓解**：`worker_prefetch_multiplier=1`
- **扩展**：增加 worker 数量

### 低风险

**暂停请求未及时检测**：
- **影响**：暂停延迟（几秒到几分钟）
- **可接受**：符合"优雅停止"设计目标

---

## 未来扩展路径

### Phase 2：添加 experiment 异步化

1. 创建 `Experiment` 表（含 `async_task_id` FK）
2. 实现 `src/tasks/experiment.py`
3. 复用 TaskManager 和 API 模式
4. 估计时间：1 周

### Phase 3：添加 import/benchmark

类似 experiment，各 1 周。

### 总扩展成本

- Phase 1（evaluation）：3-4 周
- Phase 2-4（其他类型）：3 周
- **总计**：6-7 周

---

## 总结

本设计通过引入 Celery + Redis 异步任务队列，解决了长时间评估任务的 HTTP 超时问题。核心特性包括：

- ✅ 立即返回的 API 端点（< 1 秒）
- ✅ 实时状态和进度查询
- ✅ 优雅的暂停/恢复机制
- ✅ 统一的任务管理抽象（支持未来扩展）
- ✅ 完善的错误处理和重试策略
- ✅ 与现有 TaskService 的深度集成

实现时间：3-4 周，测试覆盖率 ≥ 80%，部署文档完善。
