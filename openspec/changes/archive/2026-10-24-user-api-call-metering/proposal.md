## Why
日/月调用字段为空，需要持久化个人模型用量并明确周期边界。
## What Changes
- 按用户统计真实生成请求，失败与重试计数，缓存、列表和验证排除。
- 持久化 UTC 日/月聚合，现有 quotas 返回用量与周期，无新增限额。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/llm-call-metrics`: 用户日/月计量。
## Impact
认证存储、凭证解析、客户端内部回调、quotas、测试及文档。用户已选择新增存储结构继续 tweak。
