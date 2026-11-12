## MODIFIED Requirements

### Requirement: 统计口径与落库结果一致

系统 SHALL 从已落库单元计算成功率、token、执行时间和失败模式。成功率的分母 SHALL 为参与统计的单元数，分子 SHALL 为 `status == "success"` 的单元数。`not_evaluable` 单元 SHALL 保留在题目列表和分页总数中，详情 SHALL 展示缺少用例的原因。该状态 SHALL 从成功率分母、难度与标签分组的通过率分母及失败汇总中排除。`cost_unknown` 的单元 SHALL NOT 被计入美元合计，响应 SHALL 标出其数量。迭代统计 SHALL 只聚合 `metrics.iterations`；该字段缺失时 SHALL 视为未知，不得用 0 或 1 代替。

#### Scenario: 成功与失败混合时的成功率

- **WHEN** 一次运行有 3 个成功单元和 1 个失败单元
- **THEN** 成功率统计为 0.75，成功数为 3，总数为 4

#### Scenario: 未知成本不计入美元合计

- **WHEN** 一个单元标记 `cost_unknown`，另一个单元的 `cost_usd` 为 0.2
- **THEN** 美元合计为 0.2，且响应标出 1 个成本未知的单元

#### Scenario: 缺少迭代次数字段

- **WHEN** 历史结果行的 metrics 没有 `iterations`
- **THEN** 迭代统计把该单元计为未知，不把它显示为 0 次迭代

#### Scenario: 保留不可评估单元的明细

- **WHEN** 一次运行有 1 个成功单元、1 个失败单元和 1 个零用例单元
- **THEN** 通过率为 0.5，分母为 2，题目分页总数为 3，零用例单元有可见原因且不计入失败汇总
