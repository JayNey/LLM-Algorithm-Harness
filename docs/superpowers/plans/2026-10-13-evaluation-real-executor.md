---
change: evaluation-real-executor
design-doc: docs/superpowers/specs/2026-10-13-evaluation-real-executor-design.md
base-ref: b76aabbddf104e526b3ac59433c34dcf90f71f07
---

# 真实评估执行体 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `run_evaluation_task` 的占位 mock worker 替换为经 `AlgorithmHarness` 执行内核的真实逐单元评估，产出真实度量落 `EvaluationResult`、累计真实 `spent_usd`、复用既有预算暂停与 resume 语义。

**Architecture:** 保留 `run_evaluation_task` 现有的 DB 中心 `TaskService` 逐单元编排（Option A）。task 启动时 fail-fast 解析 model+凭证、构造 `AlgorithmHarness`、每策略一次 `_prepare_strategy_runtime` 缓存 runtime、经 `ProblemStore` 解析题目；worker（executor 线程，不触碰 db）调 `_execute_problem` + `_estimate_cost` 返回 `ExecutionResult`；`on_unit_finished`（主线程）幂等 upsert `EvaluationResult` 并聚合 `completed_count`/`failed_count`/`spent_usd`。

**Tech Stack:** Python 3.11+、Celery、SQLAlchemy 2.0、Alembic、Pydantic v2、FastAPI、pytest。

**Spec:** docs/superpowers/specs/2026-10-13-evaluation-real-executor-design.md（权威技术设计）；canonical 需求见 openspec/changes/evaluation-real-executor/specs/api/evaluation-execution/spec.md 与 .../database-schema/spec.md。

## Global Constraints

- 代码风格：`black`（line-length 100）+ `ruff` + `isort`；类型检查 `mypy src/ --ignore-missing-imports`。
- 所有文件 IO 显式 `encoding="utf-8"`（CI 门禁 `scripts/find_missing_encoding.py` + `tests/test_utf8_io.py`）。
- 测试**全程 mock LLM 与沙箱，不发起任何在线调用**（`pytest -m "not online"`）。
- `TaskService.run` 的 `max_workers` 必须保持 **1**（预算严格暂停前提，task_service.py:343-345）。
- **worker 运行在 executor 线程，禁止触碰 `db` session**；所有 DB 写在主线程 `on_unit_finished`。
- 本次**不持久化、不接入** `timeout_seconds` / `max_concurrency`。
- `HarnessConfig.budget_cap_usd` 保持 `None`（预算走 DB 中心 `should_pause`，不用 harness `RunCostMonitor`）。
- BREAKING：`EvaluationCreateRequest.model` 为必填；DB 列对既有行可空。
- 新 Alembic 迁移 `down_revision = "3a568a0f1b04"`（当前 head）。

## Review Focus

1. **worker 线程 DB 安全**：worker 若误用 `db` session 会导致跨线程 SQLAlchemy 损坏 → 断言 worker 闭包不引用 `db`，所有写在 `on_unit_finished`（Task 6 测试）。
2. **成本无定价诚实口径**：`_estimate_cost` 无 pricing 时 `cost=0`+`cost_unknown=True`，`spent_usd` 不伪造增长、不触发暂停（Task 5 测试）。
3. **计数口径**：`completed_count` 只数 `TaskUnit.status=="completed"`，`failed_count` 只数 `"failed"`，二者之和==已完成单元数；不得沿用 `record.completed_units`（含失败）（Task 4 测试）。
4. **resume 不重复**：resume 后已完成单元不重跑、不产生重复 `EvaluationResult` 行、`spent_usd`/计数续增不重置（Task 7 测试）。
5. **凭证异常不外泄 HTTP 语义**：`llm_config` 抛 `HTTPException` 必须转 `ValueError` → 评估 `failed`、不触发 Celery 重试、无单元结果（Task 3 测试）。

---

### Task 1: Evaluation.model 列 + Alembic 迁移

**Files:**
- Modify: `api/db/models.py`（`Evaluation`，第 64-88 行区块）
- Create: `api/db/migrations/versions/c0003_add_evaluation_model.py`
- Test: `tests/test_api_database.py`

**Interfaces:**
- Produces: `Evaluation.model: Mapped[str | None]`（`String(200)`，可空）；迁移 `revision="0003"`、`down_revision="3a568a0f1b04"`。

- [ ] **Step 1: 写失败测试**（迁移往返 + 列存在）

```python
def test_evaluation_model_column_roundtrip(tmp_path):
    from api.db import make_engine, run_migrations, downgrade
    from api.db.models import Evaluation
    engine = make_engine(f"sqlite:///{tmp_path/'biz.db'}")
    run_migrations(engine)
    insp = sa.inspect(engine)
    assert "model" in {c["name"] for c in insp.get_columns("evaluations")}
    # 迁移可 downgrade 回 base 再 upgrade head 无报错
    downgrade(engine, "base")
    run_migrations(engine)
    assert "model" in {c["name"] for c in sa.inspect(engine).get_columns("evaluations")}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python3 -m pytest tests/test_api_database.py::test_evaluation_model_column_roundtrip -v --no-cov`
Expected: FAIL（`model` 列不存在）

- [ ] **Step 3: 加模型列**——在 `Evaluation` 的 `api_key_id` 附近增加：
```python
model: Mapped[str | None] = mapped_column(String(200))
```

- [ ] **Step 4: 写迁移**——`c0003_add_evaluation_model.py`：`revision="0003"`、`down_revision="3a568a0f1b04"`；`upgrade` 用 `op.add_column("evaluations", sa.Column("model", sa.String(length=200), nullable=True))`；`downgrade` 用 `op.drop_column("evaluations", "model")`。SQLite 若报错则退回 `with op.batch_alter_table("evaluations") as batch_op:`。参照 `api/db/migrations/versions/3a568a0f1b04_add_async_tasks_table.py` 的文件头风格。

- [ ] **Step 5: 运行测试确认通过**

Run: `python3 -m pytest tests/test_api_database.py::test_evaluation_model_column_roundtrip -v --no-cov`
Expected: PASS

- [ ] **Step 6: 提交**
```bash
git add api/db/models.py api/db/migrations/versions/c0003_add_evaluation_model.py tests/test_api_database.py
git commit -m "feat(db): add nullable model column to evaluations (evaluation-real-executor 1.1)"
```

---

### Task 2: EvaluationCreateRequest.model 必填 + 持久化

**Files:**
- Modify: `api/models.py`（`EvaluationCreateRequest`）
- Modify: `api/services/evaluation_service.py:182-196`（`create_evaluation`）、`:279-293`（`create_evaluation_async`）
- Test: `tests/test_api_evaluation*.py`（或最贴近的现有评估 service 测试文件）

**Interfaces:**
- Consumes: `Evaluation.model`（Task 1）
- Produces: `EvaluationCreateRequest.model: str`（必填，`min_length=1`）；两个创建路径持久化 `model`。

- [ ] **Step 1: 写失败测试**

```python
def test_create_evaluation_persists_model(service, owner_id):
    req = EvaluationCreateRequest(api_key_id="k1", problem_ids=["p1"],
                                  strategy_names=["vanilla"], model="gpt-4o-mini")
    resp = service.create_evaluation(req, owner_id)
    assert resp.model == "gpt-4o-mini"

def test_create_evaluation_requires_model():
    with pytest.raises(ValidationError):
        EvaluationCreateRequest(api_key_id="k1", problem_ids=["p1"], strategy_names=["vanilla"])
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/ -k "create_evaluation_persists_model or create_evaluation_requires_model" -v --no-cov`
Expected: FAIL

- [ ] **Step 3: 加请求字段**——`EvaluationCreateRequest` 增加 `model: str = Field(..., min_length=1, description="Model name used to execute the evaluation")`。若 `EvaluationResponse`/`_to_response` 未含 `model`，一并补上以便断言。

- [ ] **Step 4: 两处持久化**——在 `create_evaluation`（:182）与 `create_evaluation_async`（:279）的 `Evaluation(...)` 构造中加 `model=request.model`。

- [ ] **Step 5: 运行确认通过**

Run: `python3 -m pytest tests/ -k "create_evaluation" -v --no-cov`
Expected: PASS

- [ ] **Step 6: 提交**
```bash
git add api/models.py api/services/evaluation_service.py api/schemas.py tests/
git commit -m "feat(api)!: require and persist model on evaluation create (evaluation-real-executor 1.2)"
```

---

### Task 3: 执行上下文 fail-fast 解析（model + 凭证 + 题目）

**Files:**
- Modify: `src/tasks/evaluation.py`（新增模块级 helper `_resolve_execution_context`）
- Test: `tests/test_celery_tasks.py`（或现有 run_evaluation_task 测试文件）

**Interfaces:**
- Produces:
  - `_resolve_execution_context(evaluation, session_factory) -> _EvalContext`
  - `_EvalContext`（dataclass）：`llm_config: LLMConfig`、`problem_map: dict[str, Problem]`、`missing_problems: set[str]`
  - 抛 `ValueError`（model 缺失 / 凭证不可解析）；调用方在既有 `except (ValueError, FileNotFoundError)` 分支置 failed。

- [ ] **Step 1: 写失败测试**

```python
def test_missing_model_fails_fast(make_evaluation):
    ev = make_evaluation(model=None)
    with pytest.raises(ValueError, match="no model"):
        _resolve_execution_context(ev, session_factory)

def test_credential_unresolvable_fails_fast(make_evaluation, monkeypatch):
    ev = make_evaluation(model="m", api_key_id="bad")
    monkeypatch.setattr(AuthService, "llm_config",
                        lambda *a, **k: (_ for _ in ()).throw(HTTPException(403, "nope")))
    with pytest.raises(ValueError, match="Credential unavailable"):
        _resolve_execution_context(ev, session_factory)

def test_missing_problem_recorded_not_fatal(make_evaluation, fake_store):
    ev = make_evaluation(model="m", problem_ids=["p1", "missing"])
    ctx = _resolve_execution_context(ev, session_factory)   # 不抛
    assert "missing" in ctx.missing_problems and "p1" in ctx.problem_map
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "fails_fast or missing_problem_recorded" -v --no-cov`
Expected: FAIL（helper 未定义）

- [ ] **Step 3: 实现 `_resolve_execution_context`**（Design Doc §5.4 + §5.5）
```python
def _resolve_execution_context(evaluation, session_factory) -> _EvalContext:
    if not evaluation.model:
        raise ValueError(f"Evaluation {evaluation.id} has no model configured")
    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from fastapi import HTTPException
    auth = AuthService(AuthSettings())
    try:
        llm_config = auth.llm_config(evaluation.api_key_id, evaluation.user_id, evaluation.model)
    except HTTPException as exc:
        raise ValueError(f"Credential unavailable: {exc.detail}") from None
    store = ProblemStore(session_factory)
    problem_map, missing = {}, set()
    for pid in evaluation.problem_ids:
        p = store.get_by_problem_id(pid)
        (problem_map.__setitem__(pid, p) if p is not None else missing.add(pid))
    return _EvalContext(llm_config=llm_config, problem_map=problem_map, missing_problems=missing)
```

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "fails_fast or missing_problem_recorded" -v --no-cov`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "feat(eval): fail-fast model+credential resolution, per-problem store lookup (evaluation-real-executor 2.1)"
```

---

### Task 4: 逐单元结果映射 + 幂等 upsert + 聚合计数

**Files:**
- Modify: `src/tasks/evaluation.py`（新增 `_record_unit_result(db, evaluation, unit)`）
- Test: `tests/test_celery_tasks.py`

**Interfaces:**
- Consumes: `EvaluationResult`（api/db/models.py:91）、`TaskUnit`
- Produces: `_record_unit_result(db, evaluation, unit) -> float`（返回本单元 cost，供 Task 5 累计）；幂等键 `(evaluation_id, problem_id, strategy_name)`；聚合 `completed_count`=#`status=="completed"`、`failed_count`=#`status=="failed"`。

- [ ] **Step 1: 写失败测试**

```python
def test_record_completed_unit_upserts_and_counts(db, evaluation, make_unit):
    unit = make_unit(status="completed", result={"status": "success", "total_tokens": 10,
                     "metadata": {"cost_usd": 0.01, "cost_unknown": False}})
    cost = _record_unit_result(db, evaluation, unit)
    row = db.query(EvaluationResult).filter_by(evaluation_id=evaluation.id,
              problem_id=unit.problem_id, strategy_name=unit.strategy).one()
    assert row.status == "success" and row.metrics["total_tokens"] == 10 and cost == 0.01
    # 再次调用（同键）不新增行
    _record_unit_result(db, evaluation, unit)
    assert db.query(EvaluationResult).count() == 1

def test_record_failed_unit_writes_failed_row(db, evaluation, make_unit):
    unit = make_unit(status="failed", error="Problem x not found in problem store")
    cost = _record_unit_result(db, evaluation, unit)
    row = db.query(EvaluationResult).one()
    assert row.status == "failed" and "not found" in row.error_message and cost == 0.0
    # 注：completed_count/failed_count 聚合归 on_unit_finished（Task 6），本 helper 不设计数
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "record_completed_unit or record_failed_unit" -v --no-cov`
Expected: FAIL

> **Ruling（preflight）**：`_record_unit_result` 只做 `EvaluationResult` 幂等 upsert + 返回 cost，**不**设置 `evaluation.completed_count/failed_count`；计数聚合统一在 Task 6 的 `on_unit_finished` 里按 `record.units` 全量重算（幂等、resume 无漂移，符合 Design Doc §5.11）。原 Task 4 测试的计数断言已移除，改由 Task 6 `test_run_evaluation_task_completes_all_units` 与 Task 8 `test_aggregate_counts_sum_to_total` 覆盖。

- [ ] **Step 3: 实现 `_record_unit_result`**（Design Doc §5.8 + §5.11 + §5.12）
```python
def _record_unit_result(db, evaluation, unit) -> float:
    if unit.status == "completed" and unit.result:
        data = unit.result
        meta = data.get("metadata") or {}
        status = data.get("status", "failed")
        metrics = {"success": status == "success",
                   "failure_category": data.get("failure_category"),
                   "failure_mode": data.get("failure_mode"),
                   "difficulty": data.get("difficulty"),
                   "total_tokens": data.get("total_tokens", 0),
                   "execution_time_seconds": data.get("execution_time_seconds", 0.0),
                   "cost_usd": meta.get("cost_usd", 0.0),
                   "cost_unknown": meta.get("cost_unknown", False),
                   "formal_evaluable": data.get("formal_evaluable", False),
                   "quality_metrics": data.get("quality_metrics")}
        error_message, cost = data.get("error_message"), float(meta.get("cost_usd", 0.0))
    else:
        status, metrics, error_message, cost = "failed", None, unit.error, 0.0
    row = db.query(EvaluationResult).filter_by(evaluation_id=evaluation.id,
              problem_id=unit.problem_id, strategy_name=unit.strategy).first()
    if row is None:
        row = EvaluationResult(id=str(uuid.uuid4()), evaluation_id=evaluation.id,
                               problem_id=unit.problem_id, strategy_name=unit.strategy)
        db.add(row)
    row.status, row.metrics, row.error_message = status, metrics, error_message
    return cost
```
聚合计数在 `on_unit_finished`（Task 6）里按 `record.units` 重算并写回 `evaluation.completed_count`/`failed_count`。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "record_completed_unit or record_failed_unit" -v --no-cov`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "feat(eval): idempotent per-unit EvaluationResult upsert + aggregate counts (evaluation-real-executor 2.2)"
```

---

### Task 5: harness 构造 + 真实 worker + 成本累计 + 预算暂停

**Files:**
- Modify: `src/tasks/evaluation.py`（新增 `_build_harness(ctx, strategy_names)` 与真实 `worker`；`should_pause` 复用既有）
- Test: `tests/test_celery_tasks.py`

**Interfaces:**
- Consumes: `_EvalContext`（Task 3）、`AlgorithmHarness._prepare_strategy_runtime/_execute_problem/_estimate_cost`
- Produces:
  - `_build_harness(ctx, strategy_names) -> tuple[AlgorithmHarness, dict[str,StrategyConfig], dict[str,tuple[Any,Any]]]`（harness、strategy_configs、runtimes）
  - 真实 `worker(unit) -> ExecutionResult`（在 `result.metadata` 写 `cost_usd`/`cost_unknown`）

- [ ] **Step 1: 写失败测试**（patch `_execute_problem` + `_estimate_cost`，不触网）

```python
def test_worker_returns_real_result_with_cost(monkeypatch, ctx, harness_ctx):
    harness, scs, runtimes = harness_ctx
    monkeypatch.setattr(harness, "_execute_problem",
        lambda sc, prob, strat, sb: ExecutionResult(problem_id=prob.problem_id,
            strategy=sc.name, generated_code="x", status="success"))
    monkeypatch.setattr(harness, "_estimate_cost", lambda results: (0.02, {"unknown_usage": False}))
    worker = make_worker(harness, scs, runtimes, ctx.problem_map)
    res = worker(make_unit(problem_id="p1", strategy="vanilla"))
    assert res.status == "success" and res.metadata["cost_usd"] == 0.02
    assert res.metadata["cost_unknown"] is False

def test_worker_missing_problem_raises(ctx, harness_ctx):
    worker = make_worker(*harness_ctx, ctx.problem_map)   # problem_map 缺 "ghost"
    with pytest.raises(ValueError, match="not found in problem store"):
        worker(make_unit(problem_id="ghost", strategy="vanilla"))

def test_budget_pause_stops_scheduling(...):
    # 2 单元，budget_cap_usd=0.01，每单元 cost=0.02 → 第1单元后触顶，第2单元不执行，终态 paused
    ...
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "worker_returns_real or worker_missing_problem or budget_pause" -v --no-cov`
Expected: FAIL

- [ ] **Step 3: 实现 `_build_harness`**（Design Doc §5.6）
```python
_UNUSED_DATASET_PATH = "db://evaluations"   # 模块级常量；从不被读取

def _build_harness(ctx, strategy_names):
    strategy_configs = {n: StrategyConfig(name=n) for n in strategy_names}
    config = HarnessConfig(llm_config=ctx.llm_config, sandbox_config=SandboxConfig(),
        dataset_path=_UNUSED_DATASET_PATH, strategies=list(strategy_configs.values()),
        budget_cap_usd=None, enable_quality_analysis=False)
    harness = AlgorithmHarness(config)
    runtimes = {n: harness._prepare_strategy_runtime(sc) for n, sc in strategy_configs.items()}
    return harness, strategy_configs, runtimes
```

- [ ] **Step 4: 实现真实 `worker`**（Design Doc §5.7；闭包只读 harness/scs/runtimes/problem_map，不引用 db）
```python
def worker(unit: TaskUnit) -> ExecutionResult:
    problem = problem_map.get(unit.problem_id)
    if problem is None:
        raise ValueError(f"Problem {unit.problem_id} not found in problem store")
    sc = strategy_configs[unit.strategy]
    strategy, sandbox = runtimes[unit.strategy]
    result = harness._execute_problem(sc, problem, strategy, sandbox)
    cost, meta = harness._estimate_cost([result])
    result.metadata["cost_usd"] = cost
    result.metadata["cost_unknown"] = bool(meta.get("unknown_usage") or meta.get("unknown_pricing"))
    return result
```
`should_pause` 保持既有实现（读 `evaluation.spent_usd >= budget_cap_usd`）；`spent_usd` 在 Task 6 的 `on_unit_finished` 里用 `_record_unit_result` 返回的 cost 累计。

- [ ] **Step 5: 运行确认通过**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "worker_returns_real or worker_missing_problem or budget_pause" -v --no-cov`
Expected: PASS

- [ ] **Step 6: 提交**
```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "feat(eval): real harness-backed worker with honest cost + budget pause (evaluation-real-executor 2.3)"
```

---

### Task 6: 接入 run_evaluation_task（替换 mock worker + on_unit_finished 落库 + 终态回写）

**Files:**
- Modify: `src/tasks/evaluation.py`（`run_evaluation_task`；并修订 `_resolve_execution_context` 补 ORM→domain 转换）
- Test: `tests/test_celery_tasks.py`（沿用既定约定，不新建 test_evaluation_task.py）

**Interfaces:**
- Consumes: `_resolve_execution_context`（本任务修订：`problem_map` 改为装 domain `src.models.Problem`）、`_build_harness`、`_make_worker`、`_record_unit_result`
- Produces: `run_evaluation_task` 三种终态（completed/paused/failed）正确回写 `Evaluation` + `AsyncTask`；`on_unit_finished` 累计 `spent_usd` + 重算 `completed_count`/`failed_count`；`_to_domain_problem(row) -> src.models.Problem`。

> **Ruling（build 发现的设计缺口，见 Design Doc §5.5）**：Task 3 的 `_resolve_execution_context` 把 `ProblemStore.get_by_problem_id` 返回的 **ORM** `api.db.models.Problem` 直接放进 `problem_map`，但 Task 5 的 worker 调 `_execute_problem` 需 **domain** `src.models.Problem`（`model_copy`/`hidden_test_cases` 等）。本任务在 `_resolve_execution_context` 内补转换：新增 `_to_domain_problem(row)` = 用 ORM 列（`problem_id/title/description/difficulty/tags/constraints/test_cases/source_platform/source_url`）组 dict 后 `src.models.Problem(**data)`（domain `migrate_legacy_test_cases` validator 会把 `test_cases` 归为 public）；转换抛 `pydantic.ValidationError` 时把该 pid 并入 `missing_problems`（数据不可用，不 fail-fast）。字段均为 eagerly-loaded 列，session 关闭后读取安全。相应更新 Task 3 的 `_resolve_execution_context` 测试：`_FakeStore` 改为返回 ORM 形状行，断言 `ctx.problem_map[pid]` 是 domain `src.models.Problem` 且 `migration_status=="legacy_test_cases_as_public"`。

- [ ] **Step 0: 先写/改转换测试（RED）**——在 `tests/test_celery_tasks.py` 改 Task 3 的 `_resolve_execution_context` 用例：`_FakeStore.get_by_problem_id` 返回一个 ORM 形状对象（含上述列，`test_cases` 为 `[{"input":...,"expected_output":...}]`），断言解析后 `ctx.problem_map["p1"]` 是 `src.models.Problem` 实例、`public_test_cases` 非空、`hidden_test_cases==[]`、`migration_status=="legacy_test_cases_as_public"`；再加一例：ORM 行 `description=""`（短于 min_length=10）→ `Problem(**data)` 抛 `ValidationError` → 该 pid 落入 `ctx.missing_problems`、不进 `problem_map`。运行确认 RED（`_to_domain_problem` 未定义 / problem_map 仍是 ORM）。

- [ ] **Step 0b: 实现 `_to_domain_problem` + 修订 `_resolve_execution_context`（GREEN）**——按上方 Ruling 实现；运行 Step 0 测试转绿，且 Task 3 原有 fails_fast/missing 用例仍绿。

- [ ] **Step 1: 写失败集成测试**（patch `AuthService.llm_config`、`AlgorithmHarness._prepare_strategy_runtime`、`_execute_problem`、`_estimate_cost`、`ProblemStore`；临时 SQLite；断言无 `mock`）

```python
def test_run_evaluation_task_completes_all_units(run_task_env):
    result = run_evaluation_task(evaluation_id)   # 2x2, 全部 success
    ev = reload_evaluation(evaluation_id)
    assert ev.status == "completed" and ev.completed_count == 4 and ev.failed_count == 0
    assert db.query(EvaluationResult).count() == 4
    assert ev.spent_usd > 0
    assert result["status"] == "completed"

def test_run_evaluation_task_credential_failure_no_results(run_task_env_bad_cred):
    with pytest.raises(ValueError):
        run_evaluation_task(evaluation_id)
    ev = reload_evaluation(evaluation_id)
    assert ev.status == "failed" and db.query(EvaluationResult).count() == 0

def test_run_evaluation_task_budget_pause(run_task_env_cap):
    run_evaluation_task(evaluation_id)
    ev = reload_evaluation(evaluation_id)
    assert ev.status == "paused" and ev.completed_count < 4

def test_run_evaluation_task_unknown_pricing_honest(run_task_env_cap):
    # Task 5 交接 MINOR：_estimate_cost 返回 (0.0, {"unknown_usage": True}) 时
    # spent_usd 不伪造增长（==0.0）、不触发预算暂停，结果行 metrics["cost_unknown"] is True
    ...
```

- [ ] **Step 2: 运行确认失败**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "run_evaluation_task" -v --no-cov`
Expected: FAIL（仍是 mock worker）

- [ ] **Step 3: 改造 `run_evaluation_task`**（Design Doc §5.3）
  - 在「验证配置」后插入 `session_factory = sessionmaker(bind=db.get_bind())`（**复用 `db` 同一 engine**，保证 ProblemStore 与 evaluation 读写同一 DB；测试中 `db` 被 patch 为内存 session，用 `business_database_url()` 新建 engine 会指向真实 DB 并破坏隔离）；`ctx = _resolve_execution_context(evaluation, session_factory)`（fail-fast 走既有 except）。
  - 置 running 后：`harness, strategy_configs, runtimes = _build_harness(ctx, evaluation.strategy_names)`（异常 → 既有 except 置 failed）。
  - 定义真实 worker：`worker = _make_worker(harness, strategy_configs, runtimes, ctx.problem_map)`（Task 5 工厂；闭包捕获 harness/strategy_configs/runtimes/problem_map，不引用 db）。
  - 重写 `on_unit_finished(record, unit)`：
    ```python
    def on_unit_finished(record, unit):
        cost = _record_unit_result(db, evaluation, unit)
        evaluation.spent_usd = (evaluation.spent_usd or 0.0) + cost
        evaluation.completed_count = sum(1 for u in record.units if u.status == "completed")
        evaluation.failed_count = sum(1 for u in record.units if u.status == "failed")
        db.commit()
        self.update_state(state="PROGRESS", meta={"current": record.completed_units,
            "total": record.total_units, "message": f"Completed {record.completed_units}/{record.total_units} units"})
    ```
  - `should_pause`、`task_service.run(max_workers=1, ...)`、终态映射、`resume` 检测全部保持既有。
  - `completed` 终态补 `evaluation.completed_at = utcnow()`（若既有未设）。

- [ ] **Step 4: 运行确认通过**

Run: `python3 -m pytest tests/test_celery_tasks.py -k "run_evaluation_task" -v --no-cov`
Expected: PASS

- [ ] **Step 5: 提交**
```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "feat(eval): replace mock worker with real harness execution in run_evaluation_task (evaluation-real-executor 3.1)"
```

---

### Task 7: resume 去重（暂停后恢复只跑剩余单元）

**Files:**
- Modify: `src/tasks/evaluation.py`（resume 分支已在，验证幂等）
- Test: `tests/test_celery_tasks.py`

**Interfaces:**
- Consumes: Task 6 的 `run_evaluation_task` + `_record_unit_result` 幂等键
- Produces: resume 后无重复 `EvaluationResult` 行、`completed_count` 续增、`spent_usd` 不重置。

- [ ] **Step 1: 写失败测试**

```python
def test_resume_after_pause_runs_only_remaining(run_task_env_cap):
    run_evaluation_task(evaluation_id)          # 预算触顶 → paused，完成 N 单元
    ev = reload_evaluation(evaluation_id)
    assert ev.status == "paused"
    first_done, first_spent = ev.completed_count, ev.spent_usd
    raise_budget(evaluation_id, cap=10.0)        # 提高预算
    run_evaluation_task(evaluation_id)           # resume
    ev = reload_evaluation(evaluation_id)
    assert ev.status in ("completed", "failed")
    assert ev.completed_count + ev.failed_count == 4
    assert ev.completed_count >= first_done
    assert db.query(EvaluationResult).count() == 4   # 无重复行
    assert ev.spent_usd >= first_spent               # 续增不重置
```

- [ ] **Step 2: 运行确认失败/通过**——若 Task 6 幂等已正确，此测试应直接 PASS；若 FAIL 则说明 resume 重跑或计数重置，需修正 `on_unit_finished` 计数基于 `record.units` 全量重算（已是）与 upsert 幂等键（已是）。

Run: `python3 -m pytest tests/test_celery_tasks.py -k "resume_after_pause" -v --no-cov`
Expected: PASS（如 FAIL，按 Design Doc §5.13 修正）

- [ ] **Step 3: 提交**
```bash
git add src/tasks/evaluation.py tests/test_celery_tasks.py
git commit -m "test(eval): verify resume dedup and continued accumulation (evaluation-real-executor 3.2)"
```

---

### Task 8: 补齐受影响测试套件（mock LLM/沙箱，不触网）

**Files:**
- Modify/Create: `tests/test_celery_tasks.py`、`tests/test_api_database.py`、受影响 `tests/test_api_evaluation*.py`
- Test: 同上

**Interfaces:**
- Consumes: 全部前序任务
- Produces: 覆盖 Design Doc §8 的 10 个用例（成功/凭证失败/缺 model/部分题目缺失/预算暂停/无预算/成本无定价/resume 去重/不可恢复错误/聚合口径）。

- [ ] **Step 1: 补「成本无定价」与「聚合口径」用例**

> **Ruling（Task 1 review 遗留 Minor 的 owner）**：本 Task 额外补一条「既有库迁移不破坏历史行」用例（对应 delta spec database-schema 场景「评估模型标识落库」的非空库子句）：`upgrade(url, "3a568a0f1b04")` → 插入一行 Evaluation（model 为 NULL）→ `run_migrations(url)` → 断言该行仍在且 `model is None`。

```python
def test_unknown_pricing_does_not_advance_spent(monkeypatch, run_task_env):
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", lambda self, r: (0.0, {"unknown_usage": True}))
    run_evaluation_task(evaluation_id_cap)   # 有 budget_cap_usd
    ev = reload_evaluation(evaluation_id_cap)
    assert ev.spent_usd == 0.0
    row = db.query(EvaluationResult).first()
    assert row.metrics["cost_unknown"] is True

def test_aggregate_counts_sum_to_total(run_task_env_mixed):
    run_evaluation_task(evaluation_id)       # 部分 success 部分 worker 抛错
    ev = reload_evaluation(evaluation_id)
    assert ev.completed_count + ev.failed_count == ev.problem_count * len(ev.strategy_names)
```

- [ ] **Step 2: 运行全量评估相关测试**

Run: `python3 -m pytest tests/ -k "evaluation" -q --no-cov`
Expected: PASS（全绿）

- [ ] **Step 3: 运行 not-online 全量回归**

Run: `python3 -m pytest -m "not online" --no-cov -q`
Expected: PASS，无新增失败

- [ ] **Step 4: 提交**
```bash
git add tests/
git commit -m "test(eval): cover unknown-pricing and aggregate-count edge cases (evaluation-real-executor 4.1)"
```

---

### Task 9: CI 等价质量门禁全绿

**Files:** 无（验证任务）

- [ ] **Step 1: 运行全部等价门禁**

Run:
```bash
ruff check . && ruff format --check . && black --check . && \
mypy src/ --ignore-missing-imports && \
python3 scripts/find_missing_encoding.py && \
python3 -m pytest tests/test_utf8_io.py -q --no-cov
```
Expected: 全部 exit 0，无违规

- [ ] **Step 2: 修复任何违规**（black/ruff 自动格式：`black .`、`ruff check --fix .`、`ruff format .`），重跑 Step 1 直至全绿。

- [ ] **Step 3: 提交**（若有格式修复）
```bash
git add -A && git commit -m "style: satisfy CI gates for evaluation-real-executor (4.2)"
```

---

## Self-Review

**1. Spec coverage：**
- 「评估单元真实执行」→ Task 5+6（真实 worker，无 mock）✓
- 「模型与凭证解析」fail-fast → Task 3 ✓
- 「题目解析与缺失处理」→ Task 3（missing 集合）+ Task 5（worker 抛错）+ Task 4（failed 落库）✓
- 「逐单元结果落库与聚合」→ Task 4 ✓
- 「成本累计与预算暂停」+ 无定价边界 → Task 5 + Task 8 ✓
- 「恢复继续不重复已完成单元」→ Task 7 ✓
- 「执行终态回写」→ Task 6 ✓
- database-schema「评估模型标识落库」→ Task 1+2 ✓

**2. Step scan：** 每步单一动作 + 可检验结果；测试步给出名称与断言；代码步给出签名 + 关键值；无 TBD。

**3. Type consistency：** `_resolve_execution_context`/`_EvalContext`/`_build_harness`/`_record_unit_result`/`worker` 命名与签名跨 Task 3-7 一致；`_record_unit_result` 返回 `float`（cost）在 Task 4 定义、Task 6 消费一致。

**4. Review Focus：** 5 条均有归属测试——worker 线程 DB 安全（Task 6 集成测试隐式 + 闭包不引用 db）、成本无定价（Task 5+8）、计数口径（Task 4）、resume 不重复（Task 7）、HTTPException→ValueError（Task 3）✓

**5. Proportion：** 计划以签名 + 断言为主，正文代码块为算法关键处（映射/聚合/worker），未逐行誊写实现，长度与 Design Doc 相当。

**留待 builder 的合理选择：** 迁移 `revision` 具体值（`"0003"` 或 hash）、测试 fixture 命名、`EvaluationResponse` 是否已含 `model` 字段（若无则 Task 2 补）、`ProblemStore` 在 task 内的 session_factory 复用方式。
