# Brainstorm Summary

- Change: evaluation-real-executor
- Date: 2026-10-13

## 侦察确认的事实（代码依据）

- `AlgorithmHarness.__init__`（harness.py:67）轻量：不加载数据集、不建沙箱/LLM，只需合法 `HarnessConfig`。
- `HarnessConfig`（models.py:764）必填 `llm_config` + `dataset_path`；`strategies` 可空。`dataset_path` 仅在 `_load_problems` 时校验存在性，`__init__` 不校验 → 逐单元编排可传占位路径而不触发文件加载。
- `_prepare_strategy_runtime(strategy_config)`（harness.py:685）：**每策略一次**，建 SandboxExecutor + health_check preflight（失败抛 RuntimeError）+ LLMClient（budget_tracker 存在则包 BudgetedLLMClient）+ STRATEGY_MAP 查类（未知策略抛 ValueError），返回 `(strategy, sandbox)`，可跨单元复用。
- `_execute_problem(strategy_config, problem, strategy, sandbox)`（harness.py:701）：**每单元**，unsupported 短路 → strategy.execute（传移除 hidden_test_cases 的副本）→ 质量分析 → hidden stage 沙箱执行 → 失败分类 → 异常脱敏，返回 `ExecutionResult`。
- `_estimate_cost([result])`（harness.py:885）：从 `llm_traces` 的 `pricing_metadata` 累计真实成本，返回 `(total_cost_usd, metadata)`；无 pricing 时标 `unknown_usage` 不伪造。
- `STRATEGY_MAP`（harness.py:57）7 个策略，键为策略名；`StrategyConfig` 仅需 `name`（其余默认）。
- `ExecutionResult`（models.py:336）字段可映射 EvaluationResult.metrics：status、failure_category、failure_mode、difficulty、total_tokens、execution_time_seconds、quality_metrics、error_message。
- `run_evaluation_task`（evaluation.py）已有完整 DB 中心编排：加载 Evaluation+AsyncTask、验证、置 running、`_create_task_units` 笛卡尔积、`TaskService(root=data/tasks/{id})`、resume 检测、`on_unit_finished`（更新 completed_count + Celery PROGRESS）、`should_pause`（paused 状态 + budget_cap_usd）、`run(max_workers=1, ...)`、终态映射。**唯一缺口是 worker() 返回 `{"mock": True}`**（evaluation.py:160-168）。
- `auth.llm_config(key_id, user_id, model)`（service.py:235）**必须传 model**；stored key 只有 provider 无默认 model → Evaluation 需新增 model 字段（open 阶段 D3 已定）。
- `Evaluation` 无 model 字段；`EvaluationResult`（evaluation_id, problem_id, strategy_name, status, metrics JSON, error_message）是逐单元结果现成载体。
- `EvaluationCreateRequest` 有 timeout_seconds(默认300)/max_concurrency(默认5)，但均未持久化到 Evaluation 表。

## 确认的方案（用户已确认 2026-10-13）

- **单元执行入口 = Option A**（复用 harness 内部方法）；timeout_seconds/max_concurrency **本次都不持久化、不接入**，保持 max_workers=1。

### 候选方案对比（存档）

- **Option A（倾向）**：保留 run_evaluation_task 自己的 DB 中心 TaskService 编排，worker 真实化——task 启动时解析 model+凭证→构造 HarnessConfig→AlgorithmHarness；从 ProblemStore 加载题目；每策略调 `_prepare_strategy_runtime` 缓存 (strategy,sandbox)；worker(unit) 调 `_execute_problem`→`_estimate_cost([result])`；on_unit_finished upsert EvaluationResult + 累加 spent_usd。复用 harness 内部私有方法。
  - 优：完全贴合 spec（逐单元行/spent_usd/pause/resume/fail-fast），复用执行内核，改动集中。
  - 劣：耦合 3 个私有方法；HarnessConfig.dataset_path 需占位。
- **Option B（否决）**：委托 `harness.run(use_task_service=True)`。CLI 导向（Rich/cost panel/文件型 TaskService/dataset_path 加载/budget_action 语义），无 per-unit DB 钩子，与 DB 中心生命周期冲突，需重度适配。
- **Option C（备选）**：在 harness 上新增公开 seam（如 execute_single_unit）或独立 EvaluationExecutor，避免私有方法耦合。优：边界清晰。劣：扩大改动到 harness.py + 新增公共 API 测试，超出「仅执行体+结果落库」范围。

## 开放项（已解决）

- timeout_seconds/max_concurrency：**用户确认本次都不持久化、不接入**。max_concurrency 与「预算严格暂停需 max_workers=1」冲突；timeout_seconds 无干净映射（SandboxConfig.timeout_seconds ≤60 且 per-test-case；LLMConfig.timeout 是请求超时）。留待后续 change。

## 测试策略（候选）

- mock LLMClient + SandboxExecutor（不触网），覆盖：成功落库、预算触顶 pause、题目缺失、凭证/模型解析 fail-fast、resume 去重不重复已完成单元。

## Spec Patch（将回写）

- 在 `specs/api/evaluation-execution/spec.md` 的「成本累计与预算暂停」需求下补一个边界场景：当单元执行无可用定价元数据时，spent_usd 按诚实口径不伪造增长（可能不触发预算暂停），并标记 unknown_usage。仅补充验收场景，不改结构或范围。
