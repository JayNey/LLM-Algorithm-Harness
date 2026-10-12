# Task 3: TaskManager 抽象层

## 任务目标

创建 `TaskManager` 类来统一管理异步任务的生命周期。该类提供抽象接口来创建任务、查询状态、更新进度、暂停/取消任务等。TaskManager 是服务层与 Celery 的桥梁。

## 文件操作

**创建**：
- `src/task_manager.py` - TaskManager 类实现
- `tests/test_task_manager.py` - TaskManager 单元测试

## 接口契约

**Consumes**：
- `api.db.models.AsyncTask` - 异步任务数据模型
- `src.celery_app.celery_app` - Celery 应用实例
- `sqlalchemy.orm.Session` - 数据库会话

**Produces**：
- `TaskManager` 类，包含以下方法：
  - `create_task(task_type, entity_id, user_id, celery_task_name, ...) -> AsyncTask` - 创建并提交任务到 Celery
  - `get_task(task_id, user_id) -> AsyncTask` - 获取任务，自动同步 Celery 状态
  - `update_task_progress(task_id, progress, status) -> None` - 更新任务进度
  - `update_task_status(task_id, status, error_message) -> None` - 更新任务状态
  - `pause_task(task_id, user_id) -> AsyncTask` - 请求暂停任务
  - `cancel_task(task_id, user_id) -> AsyncTask` - 取消任务
  - `list_tasks(user_id, task_type, status, limit, offset) -> tuple[list, int]` - 列出用户任务

## 核心设计

### 状态同步

TaskManager 在 `get_task()` 时从 Celery 主动同步状态到数据库，处理以下 Celery 状态转换：
- STARTED → running (更新 started_at)
- PROGRESS → running (更新 progress dict)
- FAILURE → failed (记录错误信息和 completed_at)

### 事务处理

所有数据库操作都在事务内完成（通过 SQLAlchemy session 的 commit/flush）：
- create_task: 先创建记录，再提交到 Celery，最后提交数据库
- pause_task/cancel_task: 更新数据库状态后立即提交

### 权限控制

get_task/pause_task/cancel_task 支持可选的 user_id 参数，用于验证任务所有者

## 实现步骤

### 步骤 1-2: TDD RED 阶段
编写失败测试，包括：
- test_create_task - 创建任务并提交到 Celery
- test_get_task - 获取任务和权限验证
- test_pause_task - 暂停运行中的任务
- test_cancel_task - 取消未完成的任务
- test_list_tasks - 按用户查询任务列表
- test_update_task_progress - 更新任务进度信息

### 步骤 3-11: TDD GREEN 阶段
按计划实现 TaskManager 类及其所有方法

### 步骤 12: 提交
```bash
git add src/task_manager.py tests/test_task_manager.py
git commit -m "feat: add TaskManager抽象层"
```

## 全局约束

- Python ≥ 3.10
- Celery ≥ 5.3.0
- Redis ≥ 6.0
- **所有异步任务必须支持 pause/resume** - TaskManager 实现 pause_task
- **错误必须区分业务错误（不重试）和基础设施错误（自动重试）** - 在 Celery 任务层实现，TaskManager 记录
- **数据库操作必须在事务内完成** - 所有方法使用 session.commit()
- 所有 API 响应必须包含标准的 ApiResponse 格式 - 由 API 层处理

## 关键实现细节

### create_task 方法

```python
def create_task(
    self,
    task_type: str,           # "evaluation", "experiment", "import", "benchmark"
    entity_id: str,           # 业务实体 ID，如 evaluation_id
    user_id: str,             # 用户 ID
    celery_task_name: str,    # Celery 任务名，如 "src.tasks.evaluation.run_evaluation_task"
    celery_task_args: tuple = (),
    celery_task_kwargs: dict | None = None,
) -> AsyncTask:
    """
    流程：
    1. 创建 AsyncTask 记录，状态为 pending
    2. flush 到数据库但不提交（避免外键约束问题）
    3. 提交任务到 Celery，获得 celery_task_id
    4. 更新 AsyncTask.celery_task_id 字段
    5. commit 提交到数据库
    """
```

### get_task 方法

```python
def get_task(self, task_id: str, user_id: str | None = None) -> AsyncTask:
    """
    流程：
    1. 按 task_id 查询（如果提供 user_id，添加权限过滤）
    2. 如果任务不存在，抛出 ValueError
    3. 如果任务有 celery_task_id 且状态为 pending/running，调用 _sync_celery_state() 从 Celery 同步最新状态
    4. 返回任务记录
    """
```

### _sync_celery_state 方法（内部）

```python
def _sync_celery_state(self, task: AsyncTask) -> None:
    """
    从 Celery 读取任务状态并更新到数据库：
    - STARTED: 更新状态为 running，记录 started_at
    - PROGRESS: 更新状态为 running，更新 progress 字段
    - FAILURE: 更新状态为 failed，记录错误信息和 completed_at
    """
```

### pause_task 和 cancel_task

两个方法都涉及权限验证（user_id）和状态转换：
- pause_task: 仅允许暂停 running 状态的任务，不涉及 Celery revoke（由任务自行检查状态）
- cancel_task: 允许取消 pending/running/paused 状态的任务，调用 celery_app.control.revoke() 终止 Celery 任务

## 验收标准

- [ ] TaskManager 类创建，接受 db_session 参数
- [ ] create_task 实现，创建 AsyncTask 记录并提交到 Celery
- [ ] get_task 实现，支持权限验证和 Celery 状态同步
- [ ] update_task_progress 实现，更新进度和状态
- [ ] update_task_status 实现，更新状态和错误信息
- [ ] pause_task 实现，检查状态转换
- [ ] cancel_task 实现，调用 Celery revoke
- [ ] list_tasks 实现，支持过滤和分页
- [ ] 所有单元测试通过（8+ 测试）
- [ ] 异常处理正确（ValueError 用于业务逻辑错误）
- [ ] 所有数据库操作在事务内
- [ ] 所有变更已提交到 Git
