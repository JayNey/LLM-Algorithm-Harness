# Brainstorm Summary

- Change: async-task-queue
- Date: 2025-01-14

## 项目上下文探索

已识别的关键组件：
- **现有 API 基础设施**：FastAPI 应用（api/main.py），带有认证、文件服务、评估服务
- **现有数据库层**：SQLAlchemy + Alembic（api/db/），已有 Problem、Evaluation、EvaluationResult 三张表
- **现有任务服务**：TaskService（src/task_service.py），提供本地持久化任务编排，支持 pause/resume/cancel
- **现有 API 路由**：evaluations、auth、files

## 已确认的设计决策

### 1. 任务创建触发方式 ✅
**决策**：方案 A - 改造现有 `/api/v1/evaluations` 端点，自动异步化
- `POST /evaluations` 内部提交 Celery 任务，立即返回
- `GET /evaluations/{id}` 聚合 Celery 状态和数据库记录
- 统一资源模型：evaluation 即为异步任务
- 不提供同步执行选项（长任务不适合同步）

**数据模型变更**：
- `Evaluation` 表增加 `celery_task_id: str | None` 字段
- 通过 `run_id` 关联 `TaskService`，通过 `celery_task_id` 关联 Celery

### 2. Celery 与 TaskService 集成层次 ✅
**决策**：方案 C - 混合方式，TaskService 作为执行引擎
- Celery 任务封装 TaskService.run() 调用
- 通过 `on_unit_finished` 回调实时同步进度到数据库和 Celery 状态
- TaskService 的 JSON 文件提供详细恢复信息（fallback）
- 数据库记录用户可见的聚合状态

**架构层次**：
```
API 端点 → Celery Task → TaskService.run() → 评估执行器
              ↓               ↓
          Celery State    JSON 文件 (详细单元状态)
              ↓
         数据库 (聚合状态)
```

### 3. 暂停/恢复的 API 语义 ✅
**决策**：方案 C - 混合策略，请求暂停 + 优雅等待
- `POST /evaluations/{id}/pause` 调用 `task_service.request_cancel()`
- Celery 任务在下一个单元边界检测标志并优雅退出
- 正在执行的单元标记为 `uncertain`，resume 时重新执行
- 数据库状态：`paused`（可恢复）vs `cancelled`（不可恢复）

**响应性说明**：
- 不是"立即"暂停，但在单元边界响应（通常几秒到几分钟）
- 保证数据一致性，避免部分执行的单元
- 未来可扩展 `force=true` 参数支持强制终止

### 4. 其他任务类型的处理 ✅
**决策**：方案 A - 本次只实现 evaluation，其他类型延后
- 当前只有 evaluation 有 API 端点，其他类型仅有 CLI
- Experiment/Import/Benchmark 保持 CLI only（现状不变）
- 优先解决最耗时的 evaluation 异步化需求

**未来扩展路径**：
- Phase 2+：根据需要逐步添加其他类型的 API 端点
- 复用 Celery 配置和任务模式
- 代码组织：`src/tasks/{evaluation,experiment,import,benchmark}.py`

**设计可复用性**：
- Celery 任务模式可复用
- `Evaluation` 表结构作为其他类型的模板
- 架构支持后续扩展

### 5. 错误处理和重试策略 ✅
**决策**：方案 C - 混合策略，任务级瞬时错误自动重试，业务错误不重试

**自动重试的错误**（最多 3 次，指数退避）：
- `redis.exceptions.ConnectionError`
- `celery.exceptions.OperationalError`
- 瞬时 LLM API 错误（如 503）

**不重试的错误**：
- 配置验证错误
- 认证错误（API key 无效）
- 资源不存在错误（dataset 文件不存在）
- 预算耗尽

**单元级错误**：
- 由 TaskService 处理，单元失败不影响整体任务
- 整体任务标记为 `completed`（但包含失败单元）
- LLM API 调用失败在单元级处理，不触发任务级重试

**手动恢复**：
- 用户仍可通过 `POST /evaluations/{id}/resume` 恢复失败任务
- TaskService resume 机制自动跳过已完成单元

### 6. 任务历史记录清理策略 ✅
**决策**：方案 D - 混合策略，分层清理

**Celery 结果（Redis）**：
- 自动 TTL = 7 天
- 任务完成后 7 天自动过期，避免内存压力

**TaskService JSON 文件**：
- 与数据库记录同步删除
- `DELETE /evaluations/{id}` 时同步删除 JSON 文件
- 可选：定期清理孤儿文件

**数据库记录**：
- 默认永久保留
- 提供 `DELETE /api/v1/evaluations/{id}` 端点手动删除
- 可选配置项：`AUTO_CLEANUP_ENABLED` 和 `AUTO_CLEANUP_DAYS`
- Phase 2 可选：Celery Beat 定时清理任务

**首次实现范围**（Phase 1）：
- ✅ Celery 结果 TTL = 7 天
- ✅ DELETE 端点（删除记录 + JSON 文件）
- ⏸️ 自动清理功能延后（根据实际需要）

---

## 所有澄清问题已完成 ✅

---

## 技术方案选择

### 对比的三个方案

**方案 1：最小化改造** - 轻量集成，Evaluation 表直接存储 celery_task_id
- 优点：快速（2-3周），改动小
- 缺点：扩展到其他类型时需要重复实现，技术债累积

**方案 2：清晰分层** - 独立 async_tasks 表，任务管理抽象层
- 优点：统一抽象，扩展成本低，代码质量高
- 缺点：首次多花 1 周

**方案 3：完全重构** - 任务优先架构，破坏性变更
- 优点：架构最清晰
- 缺点：破坏性变更，风险高，5-6 周

### ✅ 最终选择：方案 2（清晰分层）

**决策理由**：
- 确认会扩展到 experiment/import/benchmark
- 统一抽象避免重复代码（4 种类型共享逻辑）
- 长期总成本更低（6-7 周 vs 10-13 周）
- 代码质量高，易于维护

**实现时间**：3-4 周（18-23 天）

---

## 确认的技术方案（方案 2 详细设计）

### 架构层次

```
API 层：/api/v1/evaluations 端点
    ↓
服务层：EvaluationService → TaskManager
    ↓
任务层：Celery Task → TaskService.run()
    ↓
数据层：async_tasks 表 + evaluations 表
```

### 数据库设计

**新增 `async_tasks` 表**：
```python
class AsyncTask(Base):
    id: str                      # 主键，UUID
    celery_task_id: str | None   # Celery 任务 ID
    task_type: str               # "evaluation", "experiment", "import", "benchmark"
    entity_id: str               # 关联的业务实体 ID（evaluation_id 等）
    user_id: str                 # 用户标识
    status: str                  # pending/running/completed/failed/paused/cancelled
    progress: dict | None        # {"current": 10, "total": 100, "message": "..."}
    error_message: str | None    # 失败原因
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

**修改 `evaluations` 表**：
- 增加 `async_task_id: str | None` 外键 → async_tasks.id

### 核心组件

**1. TaskManager（新增）**：
- `create_task()` - 创建 AsyncTask 记录并提交 Celery
- `get_task()` - 查询任务状态（聚合 Celery + 数据库）
- `pause_task()` - 请求暂停
- `resume_task()` - 恢复执行
- `cancel_task()` - 取消任务
- `update_task_progress()` - 更新进度（Celery 回调）

**2. Celery 任务（src/tasks/evaluation.py）**：
- `run_evaluation_task(evaluation_id)`
- 调用 TaskService.run()，通过回调同步状态
- 混合重试策略（基础设施错误自动重试，业务错误不重试）

**3. API 端点改造**：
- `POST /evaluations` → 创建 Evaluation + AsyncTask，提交 Celery
- `GET /evaluations/{id}` → 聚合 Evaluation + AsyncTask 状态
- `POST /evaluations/{id}/pause` → TaskManager.pause_task()
- `POST /evaluations/{id}/resume` → TaskManager.resume_task()
- `DELETE /evaluations/{id}` → 取消任务 + 删除记录

### 未来扩展路径

添加 experiment/import/benchmark 时：
1. 创建对应的业务表（含 async_task_id FK）
2. 实现对应的 Celery 任务（src/tasks/xxx.py）
3. API 端点复用 TaskManager 逻辑
4. 无需重复实现状态管理

---

## 关键取舍与风险

### 技术取舍
- **架构方案**：选择方案 2（清晰分层），虽然首次多花 1 周，但避免后期重构成本
- **Worker 并发**：低并发（1-4），避免 LLM API 限流，牺牲吞吐量
- **暂停机制**：优雅停止（单元边界），保证数据一致性，响应延迟可接受
- **状态存储**：双层（async_tasks + TaskService JSON），提供恢复保障

### 主要风险
- **高风险**：TaskService 与 Celery 状态不一致 → 实时回调同步缓解
- **中风险**：Redis 内存溢出 → 7 天 TTL + maxmemory-policy
- **低风险**：暂停响应延迟 → 符合设计目标，可接受

## 测试策略

### 单元测试
- TaskManager 所有方法（create/get/pause/resume/cancel/list）
- Celery 任务逻辑（成功/失败/重试/状态转换）
- 进度更新回调

### 集成测试
- 完整流程：创建 → 执行 → 完成
- 暂停 → 恢复流程
- 取消流程
- 错误处理（配置错误、资源不存在）

### 覆盖率目标
- ≥ 80%

## Spec Patch

### 修改现有 spec：`api/database-schema`
**新增需求**：
- REQ-DB-004: async_tasks 表存储异步任务元数据
- REQ-DB-005: evaluations 表增加 async_task_id 外键

### 创建新 spec：`api/async-task-queue`
**核心需求**（共 7 个）：
- REQ-ATQ-001: 异步任务创建（立即返回）
- REQ-ATQ-002: 实时状态查询（聚合 Celery + DB）
- REQ-ATQ-003: 任务暂停（优雅停止）
- REQ-ATQ-004: 任务恢复（跳过已完成单元）
- REQ-ATQ-005: 任务取消（删除所有记录）
- REQ-ATQ-006: 错误处理和重试（区分业务/基础设施错误）
- REQ-ATQ-007: 任务历史清理（Celery 7 天 TTL）

---

## 设计方案已完成 ✅

所有 8 个部分的详细设计已产出，等待用户确认后进入 Design Doc 编写阶段。

## 候选技术方案

（待产出）

## 关键取舍与风险

（待产出）

## 测试策略

（待产出）

## Spec Patch

（待产出）
