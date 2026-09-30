# cost-aware-strategy-selection Delta

## MODIFIED Requirements

### Requirement: 运行中预算降级

系统 SHALL 支持通过 `--budget-cap USD` 设置本次任务的累计成本上限：逐题累计已知定价的调用成本。在难度策略选择器模式下，未显式选择预算动作或显式选择 `--downgrade-on-budget` 时，达到上限后后续题目 SHALL 自动改用映射中最便宜策略执行，其结果 SHALL 标记 `cost_downgraded=true`。显式选择 `--auto-stop-on-budget` 时 SHALL 改为暂停派发新题，不执行预算降级。监控覆盖同一任务的完整成本，`--resume` 恢复时 SHALL 先回放已完成题目的成本再继续执行，不追溯其他运行的历史。

#### Scenario: 达上限后降级

- **WHEN** 选择器运行中累计已知成本达到预算上限，未显式指定预算动作，后续仍有未执行题目
- **THEN** 后续题目以映射中最便宜策略执行，结果带 `cost_downgraded=true`，已完成题目不受影响

#### Scenario: 显式自动暂停

- **WHEN** 选择器运行指定 `--auto-stop-on-budget` 且累计已知成本达到预算上限
- **THEN** 不再派发新题，保留未派发题目，已在途题目结算后任务进入 paused

#### Scenario: 未达上限不降级

- **WHEN** 选择器运行全程累计成本未达上限
- **THEN** 所有题目按映射策略执行，无结果被标记 `cost_downgraded`
