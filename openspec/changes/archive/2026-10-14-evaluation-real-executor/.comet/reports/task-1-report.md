# Task 1 实现报告 — Evaluation.model 列 + Alembic 迁移

- Change：`evaluation-real-executor`
- 分支：`comet/evaluation-real-executor`
- 提交：`6859275af711f71e32d5cc2f2d9c09d4b5204078`
- 状态：DONE

## 1. 改动摘要

为 `evaluations` 表引入可空的 `model` 列，供后续任务在解析 `auth.llm_config(key_id, user_id, model)` 时使用；DB 层可空以兼容历史行，请求层的必填约束由 §5.2（后续任务）单独引入。

1. **ORM 列**（`api/db/models.py`，`Evaluation` 类）：在 `api_key_id` 之后新增
   `model: Mapped[str | None] = mapped_column(String(200))`。`String` 已在文件顶部 `from sqlalchemy import ... String ...` 中导入，无需新增 import。
2. **Alembic 迁移**（新建 `api/db/migrations/versions/c0003_add_evaluation_model.py`）：
   - `revision = "0003"`，`down_revision = "3a568a0f1b04"`（延续 `0001 → 0002 → 3a568a0f1b04 → 0003` 链）。
   - `upgrade()`：`op.add_column("evaluations", sa.Column("model", sa.String(length=200), nullable=True))`。SQLite 原生支持「可空且无 server_default」的 `add_column`，本地 SQLite 与 CI 一致，无需退回 `batch_alter_table`；注释中保留了退回路径的说明以便未来非 SQLite 方言遇阻时参考。
   - `downgrade()`：`op.drop_column("evaluations", "model")`。
   - docstring/import 风格参照同目录 `a0001_initial.py`、`b0002_experiment_benchmark.py`、`3a568a0f1b04_add_async_tasks_table.py`；文件命名沿用字母前缀惯例（`a`/`b`/`c` + 序号）。
3. **测试**（`tests/test_api_database.py`，`TestMigrations` 类内新增两条）：
   - `test_evaluations_model_column_present_after_migration`：临时 SQLite 上 `run_migrations(url)` 后，`inspect(engine).get_columns("evaluations")` 必须包含 `model`，且 `nullable=True`、类型是 `VARCHAR`。
   - `test_evaluations_model_column_roundtrip_downgrade_upgrade`：`run_migrations → downgrade(url, "base") → run_migrations` 往返无报错，且回滚到 base 时 `evaluations` 表被 drop，重新 upgrade 后 `model` 列仍存在。
   - 全部使用 `api/db/__init__.py` 导出的真实 helper：`run_migrations`、`downgrade`、`make_engine`（`api/db/migrate.py` 中 `run_migrations(engine_or_url)` 与 `downgrade(database_url, revision="base")` 均已存在，签名一致）。

## 2. TDD 循环

### 2.1 RED（先写失败测试）

命令：
```
python3 -m pytest tests/test_api_database.py -k model_column -v --no-cov
```

失败摘要：
```
tests/test_api_database.py::TestMigrations::test_evaluations_model_column_present_after_migration FAILED
tests/test_api_database.py::TestMigrations::test_evaluations_model_column_roundtrip_downgrade_upgrade FAILED

AssertionError: evaluations.model 缺失，现有列：['api_key_id', 'async_task_id', 'budget_cap_usd',
'completed_at', 'completed_count', 'created_at', 'error_message', 'failed_count', 'id',
'problem_count', 'problem_ids', 'run_id', 'spent_usd', 'started_at', 'status',
'strategy_names', 'updated_at', 'user_id']

AssertionError: assert 'model' in {'api_key_id', 'budget_cap_usd', 'strategy_names', ...}

================= 2 failed, 9 deselected, 5 warnings in 2.52s ==================
```

失败原因与预期一致：`evaluations` 表尚无 `model` 列（既非 typo，也非环境问题）。

### 2.2 GREEN（最小实现后重跑同一命令）

命令：
```
python3 -m pytest tests/test_api_database.py -k model_column -v --no-cov
```

通过摘要：
```
tests/test_api_database.py::TestMigrations::test_evaluations_model_column_present_after_migration PASSED
tests/test_api_database.py::TestMigrations::test_evaluations_model_column_roundtrip_downgrade_upgrade PASSED
================= 2 passed, 9 deselected, 5 warnings in 2.05s ==================
```

### 2.3 全文件回归（无回归）

命令：
```
python3 -m pytest tests/test_api_database.py -q --no-cov
```

结果：
```
======================== 11 passed, 5 warnings in 3.04s ========================
```

`TestMigrations`（含既有 `test_roundtrip_on_empty_database`、`test_upgrade_sql_is_portable_to_postgresql`）、`TestProblemStore`、`TestEvaluationPersistence` 全部通过；无 warnings 与错误。

## 3. 质量门禁

- `ruff check api/db/`：`All checks passed!`
- `black --check api/db/models.py api/db/migrations/versions/c0003_add_evaluation_model.py tests/test_api_database.py`：`All done! ✨ 🍰 ✨ 3 files would be left unchanged.`
- `python3 scripts/find_missing_encoding.py`：`Implicit text encodings: 0`（本任务未引入任何文件 IO，`encoding` 约束天然满足）。

## 4. 变更文件清单

| 文件 | 类型 | 说明 |
|---|---|---|
| `api/db/models.py` | 修改 | `Evaluation` 类在 `api_key_id` 之后新增 `model: Mapped[str \| None] = mapped_column(String(200))`（+1 行） |
| `api/db/migrations/versions/c0003_add_evaluation_model.py` | 新建 | revision `0003`，down_revision `3a568a0f1b04`；upgrade 加列、downgrade 删列（+31 行） |
| `tests/test_api_database.py` | 修改 | `TestMigrations` 内新增两条 `model_column` 测试（+22 行） |

`git show --stat`：
```
 .../versions/c0003_add_evaluation_model.py         | 31 ++++++++++++++++++++++
 api/db/models.py                                   |  1 +
 tests/test_api_database.py                         | 22 +++++++++++++++
 3 files changed, 54 insertions(+)
```

## 5. 提交

- 哈希：`6859275af711f71e32d5cc2f2d9c09d4b5204078`
- 信息：`feat(db): add nullable model column to evaluations (evaluation-real-executor 1.1)`
- 仅 `git add` 允许范围内的三个文件；未触碰 `src/tasks/evaluation.py`、`api/models.py`、`api/services/evaluation_service.py` 等后续任务文件，也未勾选 plan / tasks.md 的复选框。

## 6. 风险信号自报

- 跨模块协调改动：否（改动局限在 `api/db/` 与 `tests/test_api_database.py`，未触碰其他模块）。
- 安全敏感面（认证/授权/加解密/SQL/外部输入/密钥凭证）：命中 SQL/schema 面，但仅新增一列且无查询逻辑变化；不涉及认证、授权、加解密、外部输入或密钥凭证的处理路径。
- 并发锁共享状态：否。
- 数据或 schema 迁移：命中。新增 Alembic revision `0003`（down_revision `3a568a0f1b04`），对 `evaluations` 表添加可空 `model` 列；提供对称 `downgrade`；既有 `test_roundtrip_on_empty_database` 已覆盖 upgrade→downgrade→upgrade 往返且通过。
- 公共 API 契约变更：否（本任务不改 `api/models.py`；请求层必填 `model` 是后续任务 §5.2 的 BREAKING，本任务不引入）。
- diff 超过 200 行：否（54 行新增）。
- DONE_WITH_CONCERNS 顾虑：无。

## 7. 备注（供后续任务参考，非本任务范围）

- 迁移链 head 已推进到 `0003`；后续任何新迁移的 `down_revision` 必须为 `"0003"`。
- `Evaluation.model` 目前 ORM 与 DB 皆可空；请求层 `EvaluationCreateRequest.model` 的必填约束、`EvaluationService.create_evaluation` 的持久化以及 `run_evaluation_task` 的 fail-fast 校验属 Task 2+ 的范围，本任务未触碰。
