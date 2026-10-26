## Why
Web 已保存的模型覆盖价格尚未被评估执行器读取，导致展示价格与实际成本、预算判断不一致。

## What Changes
- 评估启动及恢复时从同一业务数据库读取最新模型价格快照，优先于文件和内置价格。
- 所有策略使用同一价格快照，trace 记录实际单价和 override 来源，缓存命中按快照计价。
- 复用既有成本累计与预算控制，不更改数据库结构和 HTTP API。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `cost-estimation/custom-pricing`: Web 覆盖定价用于评估成本和预算。

## Impact
评估执行上下文、PricingManager、LLM 缓存读取及回归测试。既有全局定价目录的覆盖作用域不变。
