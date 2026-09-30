# Proposal: 按难度的成本预算分配（issue #85）

## Why

#56b（cost-aware-strategy-selector，PR #76 已合入）交付了单一全局 `--budget-cap` 与全局降级：任一题触顶后，后续所有题目统一降级到最便宜策略。issue #85 要求更精细的成本控制：每个难度独立预算、独立追踪，某难度超支只降级该难度，其他难度不受影响。

## What Changes

- 新增每难度预算配置：`harness run --difficulty-strategy ... --budget-allocation easy=2.0 medium=5.0 hard=3.0`（或配置文件 `budget_allocation` 字段，单位 USD）。
- 每个难度独立累计已知定价成本；某难度达到其预算后，仅该难度的剩余题目降级到映射中最便宜策略（复用 #56b 阶梯），其他难度继续按映射策略执行。
- 全局 `--budget-cap` 语义保持不变，两者可同时使用，任一触顶即触发降级（该题所属难度或全局）。
- 报告增强：`by_difficulty` 每桶新增累计已知成本 `cost_usd`（增量字段，向后兼容）；运行结束的 Cost control 摘要逐难度列出预算使用情况。
- 不做（issue 标记可选）：按标签的预算分配。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `cost-aware-strategy-selection`: 预算降级 Requirement 扩展为支持按难度独立预算与隔离降级；新增预算分配配置与按难度成本呈现的验收要求。

## Impact

- 代码：`src/cost_strategy.py`（每难度监控器编排）、`src/harness.py`（worker 按难度触发降级、by_difficulty 成本）、`src/main.py`（`--budget-allocation` 解析与校验）、`src/models.py`（`budget_allocation` 字段）、`tests/test_cost_strategy.py`、README。
- 兼容性：`budget_allocation` 默认 None 时行为与现状完全一致；`by_difficulty` 新键为增量；全局 cap 行为不变。
