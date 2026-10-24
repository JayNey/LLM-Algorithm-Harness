## Why
现有日/月生成调用只计量，无法限制开销，需要可配置额度及并发安全拦截。
## What Changes
- 增加每日、每月服务端调用上限，默认无限，零禁止调用。
- 在真实 SDK 尝试之前原子检查并计数，超额不发请求；查询展示生效额度。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/llm-call-metrics`: 用户日月计量扩展为强制额度。
## Impact
认证配置与存储、凭证绑定、LLM 重试边界、额度视图、测试和文档；沿用现有表，无 schema 或新接口。用户已选择继续 tweak，在独立分支实施。
