# Task 2: 数据库模型和迁移

## 任务目标

创建 `AsyncTask` SQLAlchemy 模型来管理异步任务的通用生命周期状态，并生成 Alembic 数据库迁移。修改 `Evaluation` 模型添加外键关联。

## 文件操作

**修改**：
- `api/db/models.py` - 添加 AsyncTask 模型，修改 Evaluation 模型添加外键
- `api/db/__init__.py` - 导出 AsyncTask

**创建**：
- `tests/test_async_task_model.py` - AsyncTask 模型单元测试
- `api/db/migrations/versions/aXXXX_add_async_tasks.py` - Alembic 迁移文件

## 接口契约

**Consumes**：
- `api.db.models.Base` - SQLAlchemy 基类
- `api.db.models.Evaluation` - 现有 Evaluation 模型

**Produces**：
- `api.db.models.AsyncTask` - 异步任务模型
- 数据库表：`async_tasks`
- 外键：`evaluations.async_task_id` → `async_tasks.id`

## 实现步骤

### 步骤 1: 写失败测试

创建 `tests/test_async_task_model.py` 中的测试用例，验证 AsyncTask 模型的基本功能（创建、查询、状态管理）。

### 步骤 2: 运行测试验证失败

预期失败原因：`ImportError: cannot import name 'AsyncTask'`（模型尚未存在）

### 步骤 3: 添加 AsyncTask 模型

在 `api/db/models.py` 中实现 AsyncTask 模型，包含以下字段：

- `id` (String(36), PK) - UUID，主键
- `celery_task_id` (String(255), UNIQUE) - Celery 任务 ID
- `task_type` (String(32), INDEX) - 任务类型（"evaluation", "experiment", "import", "benchmark"）
- `entity_id` (String(36), INDEX) - 关联的业务实体 ID
- `user_id` (String(64), INDEX) - 用户标识
- `status` (String(16), INDEX, default="pending") - 状态（pending/running/paused/completed/failed/cancelled）
- `progress` (JSON) - 进度信息（可选，格式：{"current": N, "total": N, "message": "..."}）
- `error_message` (Text) - 失败原因（可选）
- `created_at` (DateTime, default=utcnow) - 创建时间
- `started_at` (DateTime) - 开始执行时间（可选）
- `completed_at` (DateTime) - 完成时间（可选）
- `updated_at` (DateTime, default=utcnow, onupdate=utcnow) - 更新时间

### 步骤 4: 修改 Evaluation 模型添加外键

在 `Evaluation` 类中添加字段：

```python
async_task_id: Mapped[str | None] = mapped_column(
    String(36),
    ForeignKey("async_tasks.id", ondelete="SET NULL"),
    index=True
)
```

### 步骤 5: 更新 api/db/__init__.py 导出

在 `__all__` 列表中添加 `"AsyncTask"`

### 步骤 6: 运行测试验证通过

重新运行 Step 2 的测试，预期 PASS

### 步骤 7: 生成 Alembic migration

```bash
alembic revision --autogenerate -m "add async_tasks table"
```

### 步骤 8: 检查生成的 migration

验证迁移文件包含：
- 创建 `async_tasks` 表
- 添加 `evaluations.async_task_id` 列
- 创建外键约束
- 创建索引

### 步骤 9: 执行 migration（开发环境）

```bash
alembic upgrade head
```

验证数据库中 `async_tasks` 表成功创建

### 步骤 10: 提交

```bash
git add api/db/models.py api/db/__init__.py api/db/migrations/versions/*.py tests/test_async_task_model.py
git commit -m "feat: add AsyncTask数据库模型和migration"
```

## 全局约束

- Python ≥ 3.10
- Celery ≥ 5.3.0
- Redis ≥ 6.0
- 所有异步任务必须支持 pause/resume
- **错误必须区分业务错误（不重试）和基础设施错误（自动重试）**
- **数据库操作必须在事务内完成**
- 所有 API 响应必须包含标准的 ApiResponse 格式

## 数据库设计参考

### 状态转换图

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

### 索引策略

为以下字段创建索引以支持高效查询：
- `celery_task_id` - 唯一，用于按 Celery 任务查找
- `task_type` - 用于按任务类型过滤
- `entity_id` - 用于按业务实体查找
- `user_id` - 用于按用户过滤
- `status` - 用于按状态过滤

## 验收标准

- [ ] AsyncTask 模型类已创建，包含所有必需字段和索引
- [ ] Evaluation 模型已修改，添加 async_task_id 外键
- [ ] AsyncTask 已导出到 api/db/__init__.py
- [ ] 所有测试通过（6+ 测试）
- [ ] Alembic 迁移文件已生成
- [ ] 迁移内容正确（表、列、外键、索引）
- [ ] 本地迁移执行成功，async_tasks 表创建完成
- [ ] 所有变更已提交到 Git
