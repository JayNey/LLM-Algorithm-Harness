# Comet Design Handoff

- Change: evaluation-real-executor
- Phase: design
- Mode: compact
- Context hash: 7dacd595489ad2849f90312b1fc541c63dc19ebe0f036ea3d959daa4db0f44ee

Generated-by: comet-handoff.sh

OpenSpec remains the canonical capability spec. This handoff is a deterministic, source-traceable context pack, not an agent-authored summary.

## openspec/changes/evaluation-real-executor/proposal.md

- Source: openspec/changes/evaluation-real-executor/proposal.md
- Lines: 1-28
- SHA256: ed1e4b7e098c1eacc02e403416858ef8382cbb24633c7ffc6115c91237a0af63

```md
## Why

评估任务已能通过 Celery 异步启动并可靠入队（#149 / #181 / #182），但 `src/tasks/evaluation.py` 的 `run_evaluation_task` 仍用占位 mock `worker()` 直接返回 `{"success": True, "mock": True}` —— 评估从不真正调用 LLM、不执行沙箱、不产生成本、不写入 `EvaluationResult`。对用户而言「评估」目前是一个只把单元标记为假成功的空壳。本次补齐真实执行体，让评估名副其实，闭合 issue #149 拆分出的 ① 项。

## What Changes

- 用真实执行替换 `run_evaluation_task` 中的 mock `worker()`：按 (strategy × problem) 单元驱动 `AlgorithmHarness` 执行链，完成 LLM 调用与沙箱执行。
- 从业务库问题存储（`ProblemStore.get_by_problem_id`）把 `Evaluation.problem_ids` 解析为 `Problem`；题目缺失时按明确的单元失败处理并记录原因，不静默跳过。
- 通过 `auth.llm_config(api_key_id, owner_id, model)` 解析真实 LLM 凭证与供应商。
- **BREAKING**：新增 `model` 字段 —— `EvaluationCreateRequest` 增加必填 `model`，`evaluations` 表增加 `model` 列（含 Alembic 迁移）。当前评估没有任何模型输入，而 `llm_config` 必须传 model，真实执行无法在不补齐该字段的情况下进行。
- 逐单元写入 `EvaluationResult`（`status` / `metrics` / `error_message`），并聚合更新 `Evaluation.spent_usd` / `completed_count` / `failed_count`。
- 接入成本统计：单元执行后累计 `spent_usd`；达到 `budget_cap_usd` 时按既有 `paused` 语义停止调度后续单元，保留已完成结果。
- 保持既有 Celery 生命周期、状态机、入队时序，以及 `start` / `pause` / `resume` / `cancel` 行为不变。

## Capabilities

### New Capabilities
- `api/evaluation-execution`: 评估任务的真实执行语义 —— worker 如何解析模型与题目、逐 (strategy × problem) 单元运行、记录每单元结果与成本、在预算触顶时暂停，以及模型/题目/单元失败时的处理与状态回写。

### Modified Capabilities
- `api/database-schema`: `evaluations` 表新增 `model` 列，作为真实执行解析 LLM 凭证所需的模型标识。

## Impact

- 代码：`src/tasks/evaluation.py`（worker 真实化）、`api/services/evaluation_service.py`（新增执行编排）、`api/models.py`（请求体加 `model`）、`api/db/models.py`（`Evaluation` 加 `model` 列）、新增一条 Alembic 迁移。
- 依赖 / 系统：`AlgorithmHarness`、`ProblemStore`、`auth.llm_config`、`BudgetTracker` / 成本估算、沙箱执行器。
- API 契约：创建评估请求新增必填 `model`（BREAKING）；既有客户端需补充该字段。
- 非目标：不含 #154 预算管理 API、#155 结果查询/分析 API；不改动已完成的入队时序与状态机；测试全部 mock LLM / 沙箱，不发起在线调用。

```

## openspec/changes/evaluation-real-executor/design.md

- Source: openspec/changes/evaluation-real-executor/design.md
- Lines: 1-73
- SHA256: ead8c3d7b0f118afc3bc389b6e53a4de89db1ef45a06864a629afe4a9d47e565

```md
## Context

动机见 `proposal.md - Why`。当前状态与约束：

- `run_evaluation_task`（`src/tasks/evaluation.py`）已用 `TaskService` 做逐单元编排，带 `pause_when`、`on_unit_finished`、resume 与预算检查钩子，但 `worker()` 是返回 `{"mock": True}` 的占位实现。
- 参照实现 `experiment` 走 `ExperimentService._execute` → `ExperimentRunner.run()` → 一次性 `AlgorithmHarness(config).run()`，产出 `StrategyReport`，不落 `EvaluationResult` 行、不支持逐单元 DB 暂停/恢复。
- `AlgorithmHarness` 内部已有单题单策略执行路径（`_prepare_strategy_runtime`、`_execute_problem`）、成本估算（`_estimate_cost`）与失败分类；`result-recording` 能力已定义 `ExecutionResult` 的度量与脱敏 trace 语义。
- `ProblemStore.get_by_problem_id(problem_id) -> Problem | None` 提供题库解析；`auth.llm_config(key_id, user_id, model) -> LLMConfig` 提供凭证解析，但**必须传 model**，而 `Evaluation` 当前无 model 列。
- `EvaluationResult` 表已存在（`evaluation_id` / `problem_id` / `strategy_name` / `status` / `metrics` / `error_message`），是逐单元结果的现成载体。

## Goals / Non-Goals

**Goals:**
- 让每个 (策略 × 题目) 单元经过真实 LLM + 沙箱执行，产出真实度量并落 `EvaluationResult`。
- 复用 `TaskService` 既有的暂停/恢复/预算/进度机制满足 spec 的预算暂停与「恢复不重复已完成单元」。
- 复用 `AlgorithmHarness` 的执行、成本估算与失败分类逻辑，避免在 worker 内重写 LLM/沙箱/成本代码。

**Non-Goals:**
- 不实现 #154 预算管理 API、#155 结果查询/分析 API（仅落库，不新增读取端点）。
- 不改动 #149/#181/#182 已定稿的入队时序、状态机与 `start/pause/resume/cancel` 生命周期语义。
- 不在测试中发起任何在线 LLM/沙箱调用。

## Decisions

### D1：保留 TaskService 逐单元编排，不改为单次 harness.run()
`worker()` 真实化，`TaskService.run(...)` 的单元循环、`pause_when`、`on_unit_finished`、resume 全部保留。
- **理由**：spec 要求「每单元一条 `EvaluationResult`」「预算触顶暂停并保留已完成结果」「恢复只跑未完成单元」——这些天然是逐单元语义；`TaskService` 已提供检查点与暂停钩子。
- **备选**：镜像 experiment 的单次 `AlgorithmHarness.run()`——被否，因其一次性跑完整 config、产出策略级报告，难以映射为逐单元 DB 行、难以在中途按预算暂停并保留部分结果、也不天然支持 DB 级 resume 去重。

### D2：单元执行经由 AlgorithmHarness 执行路径，而非在 worker 内重写
每个单元通过 harness 的执行链（策略运行时准备 + 单题执行 + 成本估算 + 失败分类）产出 `ExecutionResult`，worker 负责把它映射为 `EvaluationResult` 与 `spent_usd` 增量。
- **理由**：复用已测试的成本估算与失败分类，保证与 CLI/experiment 口径一致，避免重复实现 LLM 调用与沙箱执行。
- **待 Design Doc 定稿**：具体入口是「每单元构造单策略 `HarnessConfig` 跑 harness」还是「复用 harness 内部 `_prepare_strategy_runtime`/`_execute_problem`」，取决于沙箱/客户端复用成本与耦合度权衡（见 Risks）。

### D3：模型与凭证解析——新增 model 字段并 fail-fast
`EvaluationCreateRequest` 增加必填 `model`，`Evaluation` 增加 `model` 列；执行开始即用 `auth.llm_config(api_key_id, owner_id, model)` 解析凭证。
- **理由**：`llm_config` 必须传 model，无默认来源；凭证解析失败或 model 缺失时在执行任何单元前把评估置 `failed`，符合 spec「不产生任何单元结果」。
- **备选**：按 provider 配默认模型——被否（用户已选择新增字段），因无法按评估选模型且引入隐式配置。

### D4：题目解析缺失按单元失败处理
按 `problem_ids` 经 `ProblemStore.get_by_problem_id` 解析；缺失题目的每个单元记为失败并写明原因，其余题目继续。
- **理由**：符合 spec「个别题目缺失不整体中止」，且失败计数口径清晰。

### D5：结果落库以 (evaluation_id, problem_id, strategy_name) 为幂等键
每单元结束 upsert 一条 `EvaluationResult`；`completed_count`/`failed_count`/`spent_usd` 在评估记录上按单元增量累计。
- **理由**：resume 重跑时同一单元不产生重复行、计数不重置，满足 spec「恢复继续不重复已完成单元」。

### D6：预算暂停复用 TaskService pause_when
`should_pause` 在累计 `spent_usd >= budget_cap_usd` 时返回真，`TaskService` 停止调度后续单元并把终态置 `paused`。
- **理由**：既有钩子已实现该语义，只需把真实成本接入 `spent_usd`。

### D7：测试全程 mock LLM 与沙箱
沿用 `test_harness.py`/`test_experiment.py` 的 `patch("src.harness.LLMClient")`、`patch("src.harness.SandboxExecutor")` 模式，断言 `EvaluationResult` 行、聚合计数、`spent_usd`、预算暂停与失败/恢复路径；不触网。

## Risks / Trade-offs

- [每单元跑完整 harness 可能重复创建沙箱/LLM 客户端，开销大] → Design Doc 评估复用单策略 harness 实例或直接调用 harness 内部执行方法；必要时在单元间复用沙箱与客户端。
- [真实成本依赖 LLM usage trace，供应商定价/用量缺失时 `spent_usd` 可能为 0 或未知] → 复用 `result-recording` 的「未知定价显式标记」语义；预算暂停在成本未知时可能不触发，作为已知限制记录，不伪造成本。
- [resume 去重依赖稳定单元身份] → 以 (evaluation_id, problem_id, strategy_name) 为幂等键，并复用 TaskService 检查点；重复策略名或重复题目 ID 的输入需在 Design Doc 明确处理口径。
- [BREAKING：创建评估请求新增必填 `model`] → 迁移新增列对既有行可空以不破坏历史数据，API 请求层要求必填；在 proposal 与迁移说明中标注 BREAKING。
- [`timeout_seconds`/`max_concurrency` 在请求中存在但未持久化] → 本次范围聚焦执行体，是否持久化并 honor 作为 Open Question 留待 Design Doc，不改变 spec 行为。

## Migration Plan

1. 新增 Alembic 迁移：`evaluations` 增加 `model` 列（对既有行可空），`upgrade`/`downgrade` 对称，可从空库复现。
2. `EvaluationCreateRequest` 与 `Evaluation` 模型增加 `model`；创建评估时持久化。
3. worker 执行体替换 mock；灰度上先在测试库跑通全部单元路径。
4. 回滚：还原 worker 为占位不影响已落库数据；迁移 `downgrade` 删除 `model` 列。

## Open Questions

- `timeout_seconds` / `max_concurrency` 是否需要在本次持久化并接入执行（当前请求有、模型无）？可在 Design Doc 决定，不影响 spec 行为与验收场景。
- 单元执行入口最终采用「单策略 harness 实例」还是「harness 内部方法复用」——由 Design Doc 结合沙箱/客户端复用成本定稿。

```

## openspec/changes/evaluation-real-executor/tasks.md

- Source: openspec/changes/evaluation-real-executor/tasks.md
- Lines: 1-20
- SHA256: f39bce49e172faae05fb9f0184793d6cb59beb3e5fa354b29bfcf800484ee8fd

```md
## 1. 数据模型与迁移（新增 model 字段）

- [ ] 1.1 在 `api/db/models.py` 的 `Evaluation` 增加 `model` 列，并新增一条 Alembic 迁移（`upgrade` 增加对既有行可空的 `model` 列、`downgrade` 对称删除）。验证：空库上 `alembic upgrade head` → `downgrade base` → 再 `upgrade head` 往返无报错，`evaluations.model` 存在。
- [ ] 1.2 `api/models.py` 的 `EvaluationCreateRequest` 增加必填 `model` 字段；`create_evaluation` 与 `create_evaluation_async` 持久化 `model` 到 `Evaluation`。验证：单测断言创建后 `evaluations.model` 等于请求值；缺少 `model` 的请求返回 422 校验失败。

## 2. 真实执行编排（service 层）

- [ ] 2.1 在 `EvaluationService` 增加真实执行编排 `_execute(evaluation_id, owner_id)`：先解析凭证 `auth.llm_config(api_key_id, owner_id, model)` 与题目 `ProblemStore.get_by_problem_id`，凭证不可解析或缺少 `model` 时在执行任何单元前把评估置 `failed` 并写 `error_message`。验证：单测覆盖「凭证不可解析→failed 且无 `EvaluationResult` 行」「缺 model→failed 不发起 LLM 调用」。
- [ ] 2.2 逐 (策略 × 题目) 单元经 `AlgorithmHarness` 执行路径产出 `ExecutionResult`，映射为 `EvaluationResult` 并以 `(evaluation_id, problem_id, strategy_name)` 为幂等键 upsert；聚合更新 `completed_count`/`failed_count`。题目缺失的单元记为失败并写原因、其余题目继续。验证：单测（mock LLM/沙箱）断言每单元一条结果行、计数口径 `completed+failed==单元总数`、部分题目缺失时其余单元正常执行。
- [ ] 2.3 把每单元真实花费累计到 `spent_usd`，达到 `budget_cap_usd` 时经 `TaskService` 的 `pause_when` 停止调度后续单元并置 `paused`、保留已完成结果。验证：单测覆盖「达上限→paused 且未开始单元不执行、已完成结果与 spent_usd 保留」「无上限→跑完全部单元」。

## 3. worker 接入与恢复

- [ ] 3.1 替换 `src/tasks/evaluation.py` 中 `run_evaluation_task` 的 mock `worker()`，改为驱动 2.1–2.3 的真实执行编排；保持既有状态机、入队时序与 `start/pause/resume/cancel` 语义不变，执行终态（completed/paused/failed）回写评估与关联 `AsyncTask` 一致。验证：`run_evaluation_task` 单测（mock harness/LLM/沙箱）断言三种终态回写正确、不再产生 `mock` 结果。
- [ ] 3.2 对 `paused`/`failed` 评估重新发起执行时从未完成单元继续，已完成单元不重复执行、不产生重复 `EvaluationResult`，计数与 `spent_usd` 在既有基础上续增。验证：单测——预算暂停后提高预算再 resume，仅剩余单元执行、无重复结果行、`completed_count` 续增。

## 4. 测试与质量门禁

- [ ] 4.1 补齐/更新受影响测试（`tests/test_evaluation*`、`test_api_database.py`、`test_api_auth.py` 等），全程 mock LLM 与沙箱、不发起在线调用。验证：`pytest -m "not online" --no-cov -q` 全绿。
- [ ] 4.2 通过全部 CI 等价门禁。验证：`ruff check .`、`ruff format --check`、`black --check .`、`mypy src/ --ignore-missing-imports`、`python scripts/find_missing_encoding.py`、`pytest tests/test_utf8_io.py -q --no-cov` 全部通过。

```
