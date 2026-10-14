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
