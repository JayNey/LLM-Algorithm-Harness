# Task 6 报告：接入 run_evaluation_task（真实执行体 + ORM→domain 转换）

- **状态**：DONE_WITH_CONCERNS
- **提交哈希**：`4bfd7959b6bc548ae14a2ab2008de65b1e70bd12`
- **分支 / 基线**：`comet/evaluation-real-executor`，父提交 `4c65318`
- **变更文件**：`src/tasks/evaluation.py`、`tests/test_celery_tasks.py`（严格在允许范围内）
- **diff 规模**：2 files changed, 399 insertions(+), 30 deletions(-)

## 1. 改动摘要

### A. 补 ORM→domain Problem 转换（设计缺口，Design Doc §5.5）

- 新增模块级 `_to_domain_problem(row: Problem) -> DomainProblem`：用 ORM 列
  （`problem_id/title/description/difficulty/tags(默认[])/constraints/test_cases/source_platform/source_url`）
  组 `dict[str, Any]` 后 `src.models.Problem(**data)`。domain 的
  `migrate_legacy_test_cases`(mode="before") validator 把 `test_cases` 归为
  `public_test_cases`（`hidden_test_cases==[]`、`migration_status=="legacy_test_cases_as_public"`）。
- 修订 `_resolve_execution_context` 解析循环：`row is None → missing`；否则
  `try: problem_map[pid] = _to_domain_problem(row) except ValidationError: missing.add(pid)`
  （数据非法按不可用处理，不 fail-fast）。
- `_EvalContext.problem_map` 类型标注改为 `dict[str, DomainProblem]`；`DomainProblem`
  提升为运行时导入（`from src.models import Problem as DomainProblem`），ORM `Problem`
  仅在 `TYPE_CHECKING` 下用于 `_to_domain_problem` 入参标注。

### B. 接线 run_evaluation_task（替换 mock worker）

- 验证配置后插入：`session_factory = sessionmaker(bind=db.get_bind())` + `ctx = _resolve_execution_context(...)`
  ——**复用 `db` 同一 engine**（不新建 engine，保证与内存测试 session 同一 DB）。解析抛
  `ValueError` 落入既有 `except (ValueError, FileNotFoundError)` → failed、无单元、无结果行。
- 置 running 后：`harness, strategy_configs, runtimes = _build_harness(ctx, evaluation.strategy_names)`。
  `RuntimeError`/`ValueError` 落入既有 except 置 failed（RuntimeError 不在 autoretry_for 内，不会无限重试）。
- 删除返回 `{"mock": True}` 的占位 worker，改为
  `worker = _make_worker(harness, strategy_configs, runtimes, ctx.problem_map)`（返回 `ExecutionResult`，
  由 `TaskService._serialize_result` 序列化入 `unit.result`）。
- 重写 `on_unit_finished(record, unit)`：`cost = _record_unit_result(...)` → 累计 `spent_usd` →
  **按 `record.units` 全量重算** `completed_count`/`failed_count`（不用含 failed 的 `record.completed_units`）
  → `db.commit()` → `self.update_state(PROGRESS, ...)`。
- `completed` 终态补 `evaluation.completed_at = utcnow()`（仅在为 None 时设置）；`utcnow` 从
  `api.db.models` 引入，与既有风格一致。
- **保持不变**：`should_pause`、`task_service.run(max_workers=1, ...)`、resume 检测、终态映射、返回值结构、
  异常处理骨架。

### 导入调整
`from pydantic import ValidationError`、`from sqlalchemy.orm import Session, sessionmaker`
（`sessionmaker` 从 TYPE_CHECKING 提升为运行时）、`api.db.models` 增补 `utcnow`。

## 2. 新增 / 修改测试（tests/test_celery_tasks.py）

- **改** `TestResolveExecutionContext::test_missing_problem_recorded_not_fatal`：`_FakeStore` 返回
  ORM 形状行，断言 `ctx.problem_map["p1"]` 是 `src.models.Problem`、`public_test_cases` 非空、
  `hidden_test_cases==[]`、`migration_status=="legacy_test_cases_as_public"`。
- **新增** `TestResolveExecutionContext::test_invalid_problem_row_recorded_as_missing`：ORM 行
  `description=""`（短于 min_length=10）→ `ValidationError` → pid 落入 `missing_problems`、不进 `problem_map`。
- **改** 3 个既有 mock 测试（`test_run_evaluation_task_success` / `_paused_state` / `_resume_from_paused`）：
  补 `patch("..._resolve_execution_context")` + `patch("..._build_harness")` 短路真实解析/构造
  （它们聚焦编排 + 终态映射，TaskService 已 mock；否则接线后会真跑凭证解析 + docker preflight）。
- **新增** `TestRunEvaluationTaskIntegration`（4 用例，真实 TaskService，不 mock）：
  - `test_run_evaluation_task_completes_all_units`：2 策略 × 2 题目 = 4 单元全 success →
    status=completed、completed_count==4、failed_count==0、EvaluationResult 行==4、spent_usd>0、
    返回 status==completed、每单元 `_execute_problem` 真实调用（execute_calls==4）、metrics.total_tokens==10、无 mock。
  - `test_run_evaluation_task_credential_failure_no_results`：`AuthService.llm_config` 抛 HTTPException →
    `pytest.raises(ValueError)`、status=failed、EvaluationResult 行==0、execute_calls==[]。
  - `test_run_evaluation_task_budget_pause`：cost=0.05 > cap=0.03 → 首单元后 paused、completed_count<2、
    execute_calls==1（未开始单元不执行）。
  - `test_run_evaluation_task_unknown_pricing_honest`（Task 5 交接 MINOR）：`_estimate_cost` 返回
    `(0.0, {"unknown_usage": True})` + cap=0.01 → spent_usd==0.0、status=completed（不触发预算暂停）、
    每行 `metrics["cost_unknown"] is True` 且 `cost_usd==0.0`。
  - 隔离：seed 真实 ORM `Problem` 行并 commit；patch `AuthService`/`AlgorithmHarness._prepare_strategy_runtime`
    /`_execute_problem`/`_estimate_cost`/`TaskManager`/`run_evaluation_task.update_state`；
    `monkeypatch.chdir(tmp_path)` 隔离 TaskService 文件产物。**未 patch TaskService**（真实编排单元、
    跑 worker/on_unit_finished/should_pause）。

## 3. RED（命令 + 失败摘要）

**A RED**：`python3 -m pytest tests/test_celery_tasks.py -k "resolve_execution_context or domain or missing_problem or invalid_problem" -v --no-cov`
- `test_missing_problem_recorded_not_fatal` FAILED：`assert isinstance(<api.db.models.Problem ...>, DomainProblem)` → False（problem_map 仍装 ORM 行，未转换）。
- `test_invalid_problem_row_recorded_as_missing` FAILED：`assert 'bad' in set()`（非法行未走 ValidationError→missing，直接进 problem_map）。
→ 体现特性缺失（`_to_domain_problem` 未实现 / 转换未接线）。

**B RED**：`python3 -m pytest tests/test_celery_tasks.py -k "Integration" -v --no-cov`
- `..._completes_all_units` FAILED：`assert 0 == 4`（EvaluationResult count，mock worker + 旧 on_unit_finished 不落库）。
- `..._credential_failure_no_results` FAILED：`DID NOT RAISE ValueError`（未接线 `_resolve_execution_context`）。
- `..._budget_pause` FAILED：`assert 'completed' == 'paused'`（mock worker 无真实 cost，spent_usd 不累计，不触顶）。
- `..._unknown_pricing_honest` FAILED：`assert 0 == 2`（无结果行）。
→ 体现仍 mock worker / 未接线。

## 4. GREEN

- A GREEN：上述 A 命令 6 passed（含 Task 3 原有 fails_fast 3 例仍绿）。
- B GREEN：`python3 -m pytest tests/test_celery_tasks.py -v --no-cov` → **22 passed**。

## 5. 回归

- `python3 -m pytest tests/test_celery_tasks.py -q --no-cov` → **22 passed**。
- `python3 -m pytest tests/ -q --no-cov -m "not online"` → **1650 passed, 6 skipped**（154s），无新增失败。

## 6. 门禁

- `ruff check src/tasks/evaluation.py tests/test_celery_tasks.py` → All checks passed（曾触发 I001 导入排序，已 `--fix` + 手工合并修复）。
- `black --check ...` → 2 files would be left unchanged（测试文件曾需重排，已 `black` 格式化）。
- `mypy src/ --ignore-missing-imports` → 仅 1 处既有基线错误 `api/files/parsing.py:93`（可忽略），**无新增错误**。
  （`DomainProblem(**data)` 初版触发 11 处 arg-type 错误，已通过 `data: dict[str, Any]` 标注消除。）

## 7. 风险信号自报（逐条）

- **跨模块协调**：命中。接线依赖 Task 3（`_resolve_execution_context`）、Task 4（`_record_unit_result`）、
  Task 5（`_build_harness`/`_make_worker`）与 `src.task_service.TaskService.run`/`_serialize_result` 编排契约；
  并消费 harness 私有方法 `_prepare_strategy_runtime`/`_execute_problem`/`_estimate_cost`（经 Task 5 工厂）。
- **安全敏感面**：命中（间接）。凭证经 `AuthService.llm_config` 解析；测试全程 patch，不触网、不解密真实凭证；
  `HTTPException` 在 `_resolve_execution_context` 内被转成 `ValueError`，不逃逸进 Celery。
- **并发 / 锁 / 共享状态**：命中。worker 跑在 TaskService 的 `ThreadPoolExecutor` 线程，`max_workers=1`；
  worker 闭包**不引用 db**（仅只读 problem_map/harness/runtimes），所有 DB 写在主线程 `on_unit_finished`；
  内存 SQLite（SingletonThreadPool）下 ProblemStore 新 session 与 evaluation session 共享同线程连接——
  仅在 ctx 解析（纯 SELECT，pysqlite 延迟 BEGIN）阶段使用，写入/commit 前无并发事务冲突（测试已验证）。
- **数据 / schema 迁移**：未命中。本任务不涉及迁移；`EvaluationResult` 行为 upsert，无 schema 变更。
- **公共 API 契约变更**：未命中。`run_evaluation_task` 签名与返回 dict 结构不变；`_to_domain_problem` 为模块私有。
- **diff > 200 行**：命中（+399/-30，主要为测试；src 净增约 77 行）。

## 8. 顾虑

1. **worker 是否仍不引用 db**：已确认。真实 worker 由 `_make_worker` 生成，闭包只捕获
   harness/strategy_configs/runtimes/problem_map，不含 db；`on_unit_finished`/`should_pause` 在主线程触碰 db。
2. **on_unit_finished 计数口径**：按 Design Doc §5.11 用 `record.units` 全量重算
   `completed_count`/`failed_count`（不用含 failed 的 `record.completed_units`）；Celery PROGRESS 的 `current`
   仍用 `record.completed_units`。注意语义：产出 `status="error"` 结果但 worker 未抛的单元计入 `completed_count`
   （其失败细节在 `EvaluationResult.status`/`metrics`），仅 worker 抛异常的单元计入 `failed_count`（Design Doc §7）。
3. **终态回写**：completed/paused/failed/cancelled 映射与 `task_manager.update_task_status` 保持既有；
   `completed_at` 仅在 completed 且原值为 None 时补写，避免覆盖既有时间戳。
4. **resume 未在本任务验证**：resume 检测（`existing_record.state in ("paused","failed")` → `resume=True`）
   与去重逻辑沿用既有、未改动；本任务集成测试均为首跑（`data/tasks/{id}` chdir 到 tmp_path，无既有 record），
   故 resume 真实路径未在本次集成用例中覆盖（既有 mock 用例 `test_run_evaluation_task_resume_from_paused`
   仍验证 `resume=True` 透传）。Design Doc §5.13 的 resume 去重（幂等 upsert）留待后续任务/验证阶段专门覆盖。
5. **`_to_domain_problem` 对 `source_platform=None` 的行为**：按简报字面实现——直接把 ORM 列组入 dict，
   domain `source_platform: str`（默认 "legacy"，非 Optional）。若真实 ORM 行 `source_platform` 为 NULL，
   `Problem(**data)` 会抛 `ValidationError` → 该题被并入 missing（其单元单独 failed，评估继续）。这与 §5.5
   「数据不完整/非法按不可用处理」一致，但可能把「仅 source_platform 缺失、其余合法」的题目误判为不可用。
   如后续认为该列应回落默认值，可在 `_to_domain_problem` 内对 None 做默认（本任务严格遵循简报未加此特判）。
6. **未勾选任何 plan/tasks 复选框、未派发任何子代理**（含 reviewer），符合 implementer 约束。
