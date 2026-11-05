## Why
Issue #349 指出 ToT 生成和评分调用的响应丢失，结果无法对账实际消耗。
## What Changes
- 按调用而非节点保存响应和迭代轨迹，复用现有结果汇总。
- 保留剪枝、解析失败、模型失败及预算停止前已经发生的调用。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `strategies/tree-of-thoughts`: 明确调用轨迹和成本完整性。
## Impact
仅修改 ToT 策略及回归测试；复用已有结果结构和预算接口。
