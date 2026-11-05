## Why
Issue #351：内置价格按插入顺序匹配，日期模型错误命中 gpt-4，导致费用和预算失真。

## What Changes
- 内置前缀按最长优先匹配，与自定义价格一致，保留 exact 和来源优先级。
- 覆盖重叠别名、字典顺序、未知模型和响应到费用/预算的离线链路。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `cost-estimation/custom-pricing`：明确内置前缀也采用最长匹配。

## Impact
业务代码限于 src/utils/pricing.py；沿用内置单价，不查询或更新外部报价，无新依赖。
