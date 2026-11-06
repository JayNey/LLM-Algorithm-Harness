# reporting/token-cost-estimation Specification

## Purpose
基于 token 使用量和模型定价提供成本估算能力，帮助用户评估不同策略的经济效益。

## Requirements

### Requirement: Token 图表显示成本信息

Token 消耗图表 SHALL 使用双 Y 轴显示 token 数量与费用；费用轴 SHALL 直读结果的 `llm_traces` 历史成本：每结果的已知费用为其各 trace `pricing_metadata.total_cost`（非 null 且 `usage_known` 非 False）之和，每策略绘制已知费用的平均值，trace 顶层 token 总数（已含主调用与 reflection 轮）作为用量口径。未知费用（缺 `pricing_metadata`、`total_cost` 为 null 或 `usage_known` 为 False）MUST NOT 绘制为美元值，SHALL 在图上明确标注数量；无任何已知费用时 SHALL 不绘制成本曲线并明确说明。图表 MUST NOT 维护独立定价表或按比例估算已保存结果的费用；图表费用与文字报告、结果 trace SHALL 可对账。

#### Scenario: 双 Y 轴显示 tokens 和成本

- **WHEN** 生成 Token 消耗图表
- **THEN** 图表左侧 Y 轴显示平均 token 数量，右侧 Y 轴显示对应的美元成本，两条曲线叠加显示

#### Scenario: 成本曲线使用不同颜色和标记

- **WHEN** 图表同时显示 tokens 和成本
- **THEN** token 数量使用蓝色实线，成本使用绿色虚线，图例清晰标注

#### Scenario: 历史已知费用直读

- **WHEN** 结果的 trace 携带已知 `pricing_metadata.total_cost`（如 $9）且模型不在任何定价表中
- **THEN** 成本轴显示 $9，而不是按 token 与默认价格重算的金额

#### Scenario: 已知零成本保留

- **WHEN** trace 的定价元数据表明费用已知且为 $0
- **THEN** 成本轴显示 $0，不触发任何默认比例估算

#### Scenario: reflection 用量计入统一口径

- **WHEN** 多轮结果的迭代包含 reflection 轮的 token 与定价
- **THEN** trace 顶层 token 总数与合并后的费用已包含 reflection 消耗，图表按该口径显示，不漏计也不重复计算

#### Scenario: 混合已知与未知费用

- **WHEN** 同策略内部分单元费用已知、部分缺失定价或 `usage_known` 为 False
- **THEN** 美元值只聚合已知部分，图上明确标注未知费用单元的数量，未知部分不绘制为美元金额

#### Scenario: 无已知费用

- **WHEN** 结果没有任何已知费用 trace 或未提供结果
- **THEN** 图表不绘制成本曲线，并明确说明无已知费用数据；MUST NOT 出现按默认定价估算的美元值

#### Scenario: 与文字报告对账

- **WHEN** 同一结果的已知费用同时出现在 HTML 文字报告与 Token 图表中
- **THEN** 图表绘制每题平均已知费用（文字报告合计 ÷ 该策略结果数），两者同源可换算，不存在两套独立计算链

### Requirement: 成本以美元显示并格式化

成本金额 SHALL 以美元货币格式显示，小于 $1 时显示到小数点后 4 位，大于 $1 时显示到小数点后 2 位。

#### Scenario: 小额成本显示精确值

- **WHEN** 单个问题的成本为 $0.00123
- **THEN** 显示为 "$0.0012"

#### Scenario: 大额成本显示常规格式

- **WHEN** 总成本为 $12.3456
- **THEN** 显示为 "$12.35"
