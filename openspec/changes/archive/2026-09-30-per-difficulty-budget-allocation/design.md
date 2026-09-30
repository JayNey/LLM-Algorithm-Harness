# Design: 按难度的成本预算分配

## 实现说明

### 监控器编排（src/cost_strategy.py）

- 新增 `DifficultyBudgetMonitor`：持有 `difficulty → RunCostMonitor(cap)` 字典。`add_result(result, difficulty)` 把结果成本结算进对应难度的监控器（无分配的难度直接忽略）；`over_cap_for(difficulty)` 返回该难度是否超支；`snapshot()` 输出每难度 `{budget_cap_usd, accumulated_cost_usd, downgraded_problems}`。全部可变状态沿用 `RunCostMonitor` 内部锁，编排层无共享可变状态。
- 难度无分配（未出现在 allocation 中）= 该难度无预算上限，照常追踪全局 cap。

### Harness 集成

- 选择器模式下构建全局 monitor（现逻辑不变）+ 有 `budget_allocation` 时构建 `DifficultyBudgetMonitor`。
- worker 执行前判定：`monitor.over_cap`（全局）或 `difficulty_monitor.over_cap_for(problem.difficulty)` 任一为真即降级该题；降级目标仍是映射中最便宜策略。降级首次触发分别记录日志（全局触发 vs 难度触发）。
- `_calculate_by_difficulty` 每桶新增 `cost_usd`：按难度累计结果的已知定价成本（复用监控器同口径的结算函数，提取 `cost_strategy.result_cost(result) -> tuple[float, bool]` 供监控与报告共用，`_estimate_cost` 行为不变）。

### 配置与 CLI

- `HarnessConfig.budget_allocation: Optional[Dict[str, float]]`，每值 gt=0；键校验 easy/medium/hard。
- CLI `--budget-allocation DIFF=USD...`（解析规则同 `--difficulty-strategy`）；与 `--budget-cap` 一样要求已提供难度映射，校验失败零模型调用。
- resume：分配预算同全局 cap，由 `--resume` 回放路径按难度结算（回放时难度取自题目），恢复后各难度独立生效。

### 报告与摘要

- Cost control 摘要在全局行后逐难度输出：`easy: $0.8/$2.0 (downgraded 1)` 格式；无分配的难度不输出。
- `by_difficulty` 桶新增 `cost_usd` 键（已知定价累计），既有 solved/total/success_rate 不变。

## 边界

- 分配预算与全局 cap 是两个独立约束，同时设置时以先触发者为准；不做按比例换算。
- 按标签分配（issue 标注可选）不做，留作后续。
