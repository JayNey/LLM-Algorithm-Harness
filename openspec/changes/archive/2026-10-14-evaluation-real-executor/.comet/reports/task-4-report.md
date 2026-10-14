# Task 4 报告：逐单元结果映射 + 幂等 upsert + 返回 cost

- **状态**：DONE
- **提交哈希**：`bdecbd58e4ce2ca1538f7828ee055e04b99a603e`（short `bdecbd5`）
- **分支**：comet/evaluation-real-executor（父提交 9b2fe7d）
- **测试摘要**：`tests/test_celery_tasks.py` 14 passed（含本任务新增 2 个）；门禁 ruff/black 全绿，mypy 仅剩既有基线错误。

## 1. 改动摘要

新增模块级 helper `_record_unit_result(db, evaluation, unit) -> float`（`src/tasks/evaluation.py`），
把一个终态 `TaskUnit` 映射为一行 `EvaluationResult`：

- **幂等键**：`(evaluation_id, problem_id, strategy_name)`。先 `query(...).filter_by(...).first()`；
  命中则更新字段，未命中则 `db.add(EvaluationResult(id=str(uuid.uuid4()), ...))`。同键重复调用不新增行。
- **completed 分支**（`unit.status == "completed" and unit.result`）：从 `unit.result` 提取 `status`
  与 `metrics`（success/failure_category/failure_mode/difficulty/total_tokens/execution_time_seconds/
  cost_usd/cost_unknown/formal_evaluable/quality_metrics），`cost = float(metadata.get("cost_usd", 0.0))`，
  `error_message = data.get("error_message")`。
- **failed / 无 result 分支**：`status="failed"`、`metrics=None`、`error_message=unit.error`、`cost=0.0`。
- **返回值**：本单元 cost，供 Task 5/6 累计 `spent_usd`。

### 遵守的关键裁定
- **不写 `evaluation.completed_count` / `failed_count`**：计数聚合归 Task 6 的 `on_unit_finished`
  按 `record.units` 全量重算（Design Doc §5.11，幂等、resume 无漂移）。测试相应改名并只断言写入行内容 + 返回 cost。
- **不 `db.commit()`**：提交时机属编排层（Task 6 主线程）。helper 只做 `db.add` + 字段更新；
  测试用同一 `db_session` query，依赖 SQLAlchemy autoflush 可见，无需显式 flush/commit。
- **status 短枚举**：写入的 status 忠实取 `ExecutionResult.status`（均 ≤ `String(16)`，`budget_exhausted` 恰好 16），不超长。

导入变更：`from api.db.models import AsyncTask, Evaluation` → 追加 `EvaluationResult`（运行时导入，helper 需要）。
未改动 `run_evaluation_task` 主体、mock worker、`_resolve_execution_context` 等既有代码（接线归 Task 6）。

## 2. 新增测试

文件：`tests/test_celery_tasks.py`（沿用既有 `db_session` / `evaluation_setup` fixture 风格）

- `make_unit` fixture：构造 `TaskUnit`，字段可覆盖（默认 completed）。
- `TestRecordUnitResult::test_record_completed_unit_upserts_and_counts`：
  写入 success 行、`metrics.total_tokens==10`、`metrics.success is True`、`metrics.cost_usd==0.01`、返回 `cost==0.01`；
  同键二次调用后 `db.query(EvaluationResult).count() == 1`（幂等）。
- `TestRecordUnitResult::test_record_failed_unit_writes_failed_row`：
  失败行 `status=="failed"`、`metrics is None`、`error_message` 含 "not found"、返回 `cost==0.0`；
  **不断言 evaluation 计数**（按裁定）。
- 顶部导入追加：`EvaluationResult`（api.db.models）、`TaskUnit`（src.task_service）。

## 3. RED（先失败）

命令：
```
python3 -m pytest tests/test_celery_tasks.py -k "record_completed_unit or record_failed_unit" -v --no-cov
```
失败摘要（体现「helper 未定义 / 特性缺失」）：
```
collected 14 items / 12 deselected / 2 selected
TestRecordUnitResult::test_record_completed_unit_upserts_and_counts FAILED
TestRecordUnitResult::test_record_failed_unit_writes_failed_row FAILED
E   ImportError: cannot import name '_record_unit_result' from 'src.tasks.evaluation'
================= 2 failed, 12 deselected, 1 warning in 0.55s ==================
```
失败原因正确：`_record_unit_result` 尚未定义（特性缺失），非拼写/环境问题。

## 4. GREEN（实现后通过）

同一命令：
```
TestRecordUnitResult::test_record_completed_unit_upserts_and_counts PASSED
TestRecordUnitResult::test_record_failed_unit_writes_failed_row PASSED
================= 2 passed, 12 deselected, 1 warning in 0.95s ==================
```

## 5. 回归

```
python3 -m pytest tests/test_celery_tasks.py -q --no-cov
======================== 14 passed, 1 warning in 1.45s =========================
```
（唯一 warning 为既有 `api/config.py:8` Pydantic V2 deprecation，与本任务无关。）

## 6. 门禁

- `ruff check src/tasks/evaluation.py tests/test_celery_tasks.py` → All checks passed!
- `black --check src/tasks/evaluation.py tests/test_celery_tasks.py` → 2 files would be left unchanged.
- `mypy src/ --ignore-missing-imports` → Found 1 error：
  `api/files/parsing.py:93: error: Class cannot subclass "SafeLoader"`（既有基线，协调者明示可忽略）。
  **本任务未新增任何 mypy 错误。**

## 7. 变更文件清单与 diff 规模

| 文件 | 变更 |
|------|------|
| `src/tasks/evaluation.py` | +62 / -1（导入追加 `EvaluationResult` + 新增 `_record_unit_result` helper） |
| `tests/test_celery_tasks.py` | +86 / -1（导入追加 + `make_unit` fixture + `TestRecordUnitResult` 2 测试） |

合计：2 files changed, 148 insertions(+), 2 deletions(-)。

## 8. 风险信号自报（逐条对照）

- **跨模块协调**：⚠️ 轻度命中。helper 读取 `TaskUnit.result`（Task 5 写入的 ExecutionResult 序列化 dict，
  含 `metadata.cost_usd/cost_unknown`）与写 `EvaluationResult`（api/db/models.py）。字段名已按既有代码库事实核对，
  未臆测；契约稳定性依赖 Task 5 的 `_serialize_result` 输出格式。接线（在 `on_unit_finished` 调用本 helper +
  计数聚合）归 Task 6，本任务不触碰编排层。
- **安全敏感面**（认证/授权/加解密/SQL/外部输入/密钥凭证）：未命中。无原生 SQL（全走 SQLAlchemy ORM 参数化查询），
  不处理凭证/密钥，不接收外部网络输入。
- **并发 / 锁 / 共享状态**：未命中。helper 无内部状态；实际执行 `max_workers=1`（Task 6 编排），
  且提交由主线程负责，本 helper 不 commit。幂等键设计本身即抵御 resume 重复写入。
- **数据 / schema 迁移**：未命中。仅向既有 `evaluation_results` 表写行，未改任何模型/列/迁移文件。
- **公共 API 契约变更**：未命中。`_record_unit_result` 为模块私有（下划线前缀）helper，非对外 API；
  未改动既有函数签名或 HTTP 接口。
- **diff > 200 行**：未命中。合计 148 insertions（+2 deletions），远低于 200 行。

## 9. 顾虑

1. **简报测试文件名与协调者指定不一致**：task-4-brief.md 指向 `tests/test_evaluation_task.py`（该文件不存在），
   协调者「允许修改文件范围」与验证命令均指定 `tests/test_celery_tasks.py`。已按协调者权威指令使用
   `tests/test_celery_tasks.py`，并沿用其既有 `db_session`/`evaluation_setup` fixture 风格；测试用例语义与简报骨架一致
   （仅按裁定移除计数断言、失败测试改名为 `test_record_failed_unit_writes_failed_row`）。
2. **未显式 `db.flush()`**：依 SQLAlchemy 默认 autoflush，同 session query 前会自动 flush pending 行，测试已验证可见。
   若 Task 6 在不同 session 或关闭 autoflush 的环境下调用，需在编排层保证 flush/commit 时机——属 Task 6 职责。
3. **`metrics` 中大量字段来自 `unit.result`（Task 5 产出）**：本任务对缺失键使用 `.get(..., 默认值)` 兜底，
   但真实字段口径（如 `cost_usd` 是否总存在于 metadata）最终由 Task 5 决定，需 Task 5/6 集成时联调确认。
