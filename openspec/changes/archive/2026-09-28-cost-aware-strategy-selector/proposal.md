# Proposal: 成本敏感策略选择器与运行中预算降级（#56b）

## Why

#56a（cost-optimization-advisor，PR #69）交付了基于历史数据的分析与推荐层，但 issue #56 第 4 节"成本敏感策略选择器集成到评估流程 + 实时监控成本、达到预算上限时自动降级策略"当时确认拆分为后续 change（#56b）。目前评估流程对同一数据集只能固定策略执行，无法按题目难度分配策略成本，也没有运行中的成本约束手段。

## What Changes

- 新增难度→策略映射（成本敏感策略选择器）：`harness run --difficulty-strategy easy=vanilla medium=chain_of_thought hard=multi_round_feedback`，每个题目按自身难度路由到映射策略，一题只执行一次（而非每个策略各执行一遍）。
- 新增运行中预算降级：`harness run --budget-cap <USD>`（需与映射同时使用）。逐题累计已知定价的调用成本，达到上限后，后续题目自动改用映射中最便宜的策略执行，结果标记 `cost_downgraded=true`。
- 两者默认关闭；不启用时执行路径与现状完全一致。固定预算实验（`harness experiment`）不受影响。
- 结果记录：`ExecutionResult` 新增可选字段 `cost_downgraded`（默认 false，向后兼容）；选择器模式的整体报告以 `cost_aware` 作为报告名，每条结果仍记录实际使用的策略。

## Capabilities

### New Capabilities

- `cost-aware-strategy-selection`: 评估流程中按难度映射策略选择与运行中预算降级的行为与验收要求。

### Modified Capabilities

（无——不改变既有 spec 的行为要求；未启用新参数时执行路径不变）

## Impact

- 代码：新增 `src/cost_strategy.py`（选择器 + 运行成本监控）；`src/harness.py`（TaskService 单元映射与降级覆盖、选择器模式报告）；`src/main.py`（run 子命令新参数与校验）；`src/models.py`（HarnessConfig 新字段、ExecutionResult.cost_downgraded）；新增 `tests/test_cost_strategy.py`。
- 兼容性：新参数默认关闭；`ExecutionResult` 新字段带默认值，旧结果文件可正常读取；config fingerprint 因配置快照变化而自然失效（TaskService 既有机制）。
- 文档：README 成本敏感策略章节。
