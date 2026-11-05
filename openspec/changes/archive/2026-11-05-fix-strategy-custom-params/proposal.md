## Why
Issue #348：策略消费 custom_params 后仍把内部键传入模型 SDK，导致配置后的策略在请求前失败。

## What Changes
- 在策略请求边界隔离全部已知内置控制键，保留原配置与合法 provider 扩展。
- 覆盖 Self-Consistency 直接调用及 Few-Shot、Reflexion 生成与反思路径。
- 用真实 SDK + MockTransport 验证 OpenAI、兼容服务与 Anthropic，请求参数优先级和缓存语义。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `strategies/few-shot-learning`：可配置检索参数只参与策略行为，不进入模型请求。

## Impact
StrategyBase、SelfConsistencyStrategy、LLMClient 的 Anthropic extra_body 透传及请求边界测试；不改变公共配置格式、依赖或 API。
