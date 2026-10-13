# Task 4: Celery 评估任务实现

## 任务目标

实现 `run_evaluation_task` Celery 任务，该任务是异步评估执行的核心。任务负责：
- 加载 Evaluation 记录和配置
- 创建 TaskService 任务单元
- 集成现有的 TaskService 执行引擎
- 定义进度回调和暂停检查
- 处理任务生命周期（running → paused/completed/failed）
- 与 TaskManager 同步状态

这个任务将长时间运行的评估逻辑从 HTTP 请求中解耦，通过 Celery worker 异步执行。

## 文件操作

**创建**：
- `src/tasks/__init__.py` - Celery tasks 模块包
- `src/tasks/evaluation.py` - run_evaluation_task 实现
- `tests/test_celery_tasks.py` - Celery 任务单元测试

## 接口契约

**Consumes**：
- `TaskManager` - 任务状态管理
- `api.db.models.Evaluation` - 评估业务数据
- `src.task_service.TaskService` - 任务执行引擎
- `src.celery_app.celery_app` - Celery 应用实例

**Produces**：
- `run_evaluation_task(evaluation_id: str) -> dict` - Celery 任务函数
- 返回值格式：`{"evaluation_id": str, "status": str, "completed_units": int, "total_units": int}`

## 核心设计

### 任务生命周期

```
pending (TaskManager) 
  → Celery 获取并执行 run_evaluation_task
  → running (更新 AsyncTask + Evaluation)
  → TaskService.run() 执行单元
  → 检查 should_pause() 和 budget_cap
  → on_unit_finished() 回调更新进度
  → completed/paused/failed/cancelled (更新 AsyncTask + Evaluation)
```

### 错误处理策略

- **业务错误**（ValueError, FileNotFoundError）：立即失败，不重试，记录错误信息
- **基础设施错误**（RedisConnectionError, ConnectionError）：自动重试（最多 3 次，指数退避）

### 进度报告

通过 `on_unit_finished()` 回调和 `self.update_state()` 定期向 Celery 报告进度：
- 更新数据库中的 `async_tasks.progress` 和 `evaluation.completed_count`
- 通过 Celery 的 PROGRESS 状态向客户端报告

### 暂停和取消

支持两种暂停机制：
1. 用户通过 `pause_task()` 设置 `AsyncTask.status = "paused"`
2. 预算上限触发自动暂停（`budget_cap_usd`）

`should_pause()` 定期检查这两个条件。如果暂停，TaskService 将在当前单元完成后停止。

## 实现步骤

### 步骤 1: 创建 tasks 模块
创建 `src/tasks/__init__.py` 空文件

### 步骤 2-3: TDD RED 阶段
写失败测试，验证导入失败

### 步骤 4: 实现任务基础结构
- 定义 `EvaluationTask` 基类，处理数据库连接缓存
- 使用 `@celery_app.task` 装饰器，配置重试策略
- 实现主 `run_evaluation_task` 函数框架
- 异常处理：捕获 ValueError 和 FileNotFoundError

### 步骤 5: 实现任务单元创建辅助函数
- `_create_task_units()` - 生成笛卡尔积（策略 × 问题）的 TaskUnit 列表
- `_build_evaluation_config()` - 构建传递给 TaskService 的配置字典

### 步骤 6: 实现 TaskService 集成
- 加载或创建 TaskService 任务
- 检查是否恢复之前的任务（paused/failed 状态）
- 定义 `on_unit_finished()` 回调
- 定义 `should_pause()` 检查函数
- 定义 `worker()` 占位函数（返回模拟结果）

### 步骤 7: 运行测试
验证 test_run_evaluation_task_success 通过

### 步骤 8: 提交
```bash
git add src/tasks/ tests/test_celery_tasks.py
git commit -m "feat: add Celery评估任务实现"
```

## 关键实现细节

### run_evaluation_task 流程

```python
@celery_app.task(
    bind=True,
    base=EvaluationTask,
    name="src.tasks.evaluation.run_evaluation_task",
    autoretry_for=(RedisConnectionError, ConnectionError),  # 重试基础设施错误
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_evaluation_task(self, evaluation_id: str) -> dict[str, Any]:
    # 1. 加载 Evaluation 和 AsyncTask 记录
    # 2. 验证配置（strategy_names, problem_ids）
    # 3. 创建/恢复 TaskService 任务
    # 4. 定义回调和检查函数
    # 5. 执行 TaskService.run()
    # 6. 更新最终状态
    # 7. 返回结果
```

### 数据库事务处理

- TaskManager 方法自动 commit
- Evaluation 字段修改后显式 db.commit()
- 异常时在 except 块中更新错误状态

### Celery 状态报告

- 使用 `self.update_state(state="PROGRESS", meta=progress)` 报告进度
- 进度字典包含 `{"current": N, "total": M, "message": "..."}`
- 客户端通过 TaskManager.get_task() 读取进度

## 全局约束

- **错误必须区分业务错误和基础设施错误** ✓ 
  - 业务错误（ValueError）：记录并失败，不重试
  - 基础设施错误（RedisConnectionError）：自动重试
  
- **所有异步任务必须支持 pause/resume** ✓ 
  - pause_task 设置 AsyncTask.status = "paused"
  - should_pause() 检查并暂停
  - resume 时从 TaskService 恢复
  
- **数据库操作必须在事务内** ✓ 
  - 所有 db.commit() 操作确保事务提交

## 验收标准

- [ ] `src/tasks/__init__.py` 已创建
- [ ] `run_evaluation_task` 函数已实现
- [ ] EvaluationTask 基类处理数据库连接
- [ ] Celery 重试策略正确配置（3 次重试，指数退避）
- [ ] 业务错误和基础设施错误正确分类
- [ ] TaskService 集成完成（加载/创建/恢复）
- [ ] 进度回调 on_unit_finished 实现
- [ ] 暂停检查 should_pause 实现
- [ ] Worker 占位函数返回模拟结果
- [ ] 最终状态正确更新（AsyncTask + Evaluation）
- [ ] 所有单元测试通过（4+ 测试）
- [ ] 异常处理完整（try/except/finally）
- [ ] 所有变更已提交到 Git
