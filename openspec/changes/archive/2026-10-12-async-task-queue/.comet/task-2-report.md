# Task 2 实现报告：数据库模型和迁移

## 实现概要

成功创建 `AsyncTask` SQLAlchemy 模型用于管理异步任务的通用生命周期状态，并生成 Alembic 数据库迁移。修改 `Evaluation` 模型添加外键关联。完全遵循 TDD 流程。

## 文件修改清单

### 创建的文件

1. **tests/test_async_task_model.py** - AsyncTask 模型单元测试
   - 8 个测试用例覆盖模型的创建、状态转换、JSON 字段、唯一性约束、查询和外键关联
   - 所有测试通过

2. **api/db/migrations/versions/3a568a0f1b04_add_async_tasks_table.py** - Alembic 迁移文件
   - 创建 `async_tasks` 表及所有索引
   - 为 `evaluations` 表添加 `async_task_id` 列和外键约束
   - 使用 batch 模式支持 SQLite ALTER TABLE 操作

### 修改的文件

1. **api/db/models.py**
   - 添加 `AsyncTask` 模型类（12 个字段）
   - 修改 `Evaluation` 模型添加 `async_task_id` 外键字段

2. **api/db/__init__.py**
   - 在导入中添加 `AsyncTask`
   - 在 `__all__` 列表中添加 `"AsyncTask"`

## TDD 执行流程

### RED 阶段
1. 编写 8 个失败的测试用例
2. 运行测试，确认失败原因：`ImportError: cannot import name 'AsyncTask'`
3. ✅ 测试正确失败

### GREEN 阶段
1. 在 `api/db/models.py` 中实现 `AsyncTask` 模型
2. 修改 `Evaluation` 模型添加外键
3. 更新 `api/db/__init__.py` 导出 AsyncTask
4. 生成 Alembic 迁移（使用 batch 模式支持 SQLite）
5. ✅ 所有 8 个测试通过

### REFACTOR 阶段
- 清理临时文件（generate_migration.py, temp.db）
- 修复迁移文件中的外键约束名称问题
- 验证现有数据库测试仍然通过

## 测试命令和输出

### 单元测试执行

```bash
python3 -m pytest tests/test_async_task_model.py -v --no-cov
```

**输出**：
```
tests/test_async_task_model.py::TestAsyncTaskModel::test_create_async_task_with_required_fields PASSED [ 12%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_status_transitions PASSED [ 25%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_progress_json_field PASSED [ 37%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_celery_task_id_unique PASSED [ 50%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_query_by_user_id PASSED [ 62%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_query_by_status PASSED [ 75%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_evaluation_async_task_foreign_key PASSED [ 87%]
tests/test_async_task_model.py::TestAsyncTaskModel::test_async_task_table_has_required_indexes PASSED [100%]

======================== 8 passed, 1 warning in 0.38s =========================
```

### 现有测试回归验证

```bash
python3 -m pytest tests/test_api_database.py tests/test_async_task_model.py -v --no-cov
```

**输出**：`17 passed, 6 warnings in 2.40s` ✅

### 迁移验证

手动验证迁移创建的数据库结构：

```
✓ async_tasks table created
  Columns: ['id', 'celery_task_id', 'task_type', 'entity_id', 'user_id', 'status', 'progress', 'error_message', 'created_at', 'started_at', 'completed_at', 'updated_at']
  Indexes: ['ix_async_tasks_celery_task_id', 'ix_async_tasks_entity_id', 'ix_async_tasks_status', 'ix_async_tasks_task_type', 'ix_async_tasks_user_id']
✓ evaluations.async_task_id column added
✓ Foreign key constraint created: {'name': 'fk_evaluations_async_task_id', 'constrained_columns': ['async_task_id'], 'referred_schema': None, 'referred_table': 'async_tasks', 'referred_columns': ['id'], 'options': {'ondelete': 'SET NULL'}}

✓ Migration verification completed successfully
```

## Git 提交

**Commit Hash**: `a11e27a913db1c5edcf5176be02ab39483d6bbe7`

**Commit Message**:
```
feat: add AsyncTask数据库模型和migration

- 添加 AsyncTask 模型用于异步任务生命周期管理
- 包含字段：id, celery_task_id, task_type, entity_id, user_id, status, progress, error_message, created_at, started_at, completed_at, updated_at
- 为 Evaluation 模型添加 async_task_id 外键
- 创建所有必需的索引（celery_task_id, task_type, entity_id, user_id, status）
- 生成 Alembic migration (3a568a0f1b04) 使用 batch 模式支持 SQLite
- 添加完整的单元测试验证模型功能和数据库约束
```

## 风险信号评估

### 命中的风险信号

✅ **数据或 schema 迁移** - 此任务直接涉及数据库 schema 变更

### 风险缓解措施

1. **向后兼容性**：
   - `Evaluation.async_task_id` 字段设置为 nullable，不会破坏现有数据
   - 外键使用 `ondelete="SET NULL"`，删除 AsyncTask 不会级联删除 Evaluation

2. **SQLite 兼容性**：
   - 使用 Alembic batch 模式处理 SQLite 的 ALTER TABLE 限制
   - 测试在 SQLite 环境中验证通过

3. **PostgreSQL 兼容性**：
   - 迁移脚本与 PostgreSQL 兼容（batch 模式在 PostgreSQL 中透明工作）
   - 外键约束明确命名（fk_evaluations_async_task_id）

4. **索引性能**：
   - 所有高频查询字段都创建了索引
   - celery_task_id 使用 UNIQUE 索引保证唯一性

5. **测试覆盖**：
   - 8 个单元测试覆盖所有关键功能
   - 包括约束验证、外键关联、索引存在性测试
   - 现有 9 个数据库测试保持通过，无回归

## 验收标准检查

- [x] AsyncTask 模型类已创建，包含所有必需字段和索引
- [x] Evaluation 模型已修改，添加 async_task_id 外键
- [x] AsyncTask 已导出到 api/db/__init__.py
- [x] 所有测试通过（8 个新测试 + 9 个现有数据库测试）
- [x] Alembic 迁移文件已生成（3a568a0f1b04）
- [x] 迁移内容正确（表、列、外键、索引）
- [x] 本地迁移执行成功，async_tasks 表创建完成
- [x] 所有变更已提交到 Git

## 技术决策

### 1. SQLite Batch 模式
**问题**：SQLite 不支持标准的 ALTER TABLE ADD CONSTRAINT  
**解决**：使用 Alembic batch 模式，通过表重建策略添加外键  
**影响**：迁移在 SQLite 和 PostgreSQL 上都能正确工作

### 2. 外键约束命名
**问题**：自动生成的迁移使用 None 作为约束名，downgrade 会失败  
**解决**：手动指定约束名称 `fk_evaluations_async_task_id`  
**影响**：downgrade 操作现在可以正常工作

### 3. 字段可空性
**问题**：现有 Evaluation 记录没有 async_task_id  
**解决**：async_task_id 设置为 nullable（Mapped[str | None]）  
**影响**：现有数据不受影响，新功能逐步迁移

## 性能考虑

- **索引策略**：5 个索引支持常见查询模式
  - `celery_task_id` (UNIQUE)：Celery 任务查找
  - `task_type`：按类型过滤
  - `entity_id`：按业务实体查找
  - `user_id`：按用户过滤
  - `status`：按状态过滤
  
- **JSON 字段**：`progress` 使用 JSON 类型，支持灵活的进度信息存储

## 后续工作建议

1. Task 3 将需要引用此模型创建 Celery 任务
2. 考虑为 `async_tasks` 添加复合索引优化特定查询（如 user_id + status）
3. 监控生产环境中的查询性能，根据实际使用模式调整索引

## 关注点

无重大关注点。实现完全符合需求规范，所有验收标准已满足。
