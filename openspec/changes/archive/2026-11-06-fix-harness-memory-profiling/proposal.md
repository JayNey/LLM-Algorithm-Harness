## Why

启用空间分析时，Harness 没有把当前沙箱交给质量分析器，导致最终代码缺少峰值内存。见 [#374](https://github.com/JayNey/LLM-Algorithm-Harness/issues/374)。

## What Changes

- 使用当前策略的沙箱和题目上下文对最终代码采集公开用例的内存峰值。
- 记录无法采样的原因，并维持原有判题状态。

## Capabilities

### New Capabilities

### Modified Capabilities

- `result-recording` 的最终代码质量指标包含可用的沙箱内存峰值。

## Impact

涉及 Harness 的质量后处理与入口回归测试。沿用现有沙箱采样方法与质量指标字段。
