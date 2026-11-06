## Why

[#363](https://github.com/JayNey/LLM-Algorithm-Harness/issues/363) 的成本优化报告以执行进度代替解题成功，并把费用小计当作完整金额。多策略准确率可以超过 100%，缺少定价的记录也会影响建议。

## What Changes

- 评估准确率使用已保存的成功单元和计划单元数。
- 排名仅使用有结果依据及完整正费用的组合，区分零费用与未知费用。
- 基准结果保留已有定价估算的完整性标记。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/cost-management`：规范个人成本优化报告的统计与费用证据。
- `cost-optimization`：明确零费用和无法比较的组合如何展示。

## Impact

影响个人报告、已有建议引擎及基准结果的费用元数据。复用现有结果字段和 JSON 存储。
