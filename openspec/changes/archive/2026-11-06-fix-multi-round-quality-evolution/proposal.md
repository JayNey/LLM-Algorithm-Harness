## Why

[#375](https://github.com/JayNey/LLM-Algorithm-Harness/issues/375) 中的多轮反馈运行只保存最终代码质量，导致演化分析拿不到可比较的逐轮数据。

## What Changes

- 启用质量分析时，保存 Multi-Round Feedback 每轮有效代码的质量指标，并复用最终代码对应的分析结果。
- 逐轮数据写入后再检查演化开关和可比较轮次。关闭演化时仍保留质量指标，重新生成报告时沿用该设置。
- 用真实 Harness 和分析器验证失败后成功的两轮执行、数据缺失与报告消费。

## Capabilities

### New Capabilities

### Modified Capabilities

- `result-recording` 记录逐轮质量并控制演化分析。

## Impact

涉及 Harness 的结果后处理、多轮策略和现有演化报告。沿用现有质量配置和数据模型。
