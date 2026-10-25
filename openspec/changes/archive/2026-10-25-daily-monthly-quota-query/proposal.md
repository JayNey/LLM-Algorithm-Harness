## Why
日/月调用计量已有实现，但无限额度查询遗漏 remaining，调用方无法统一读取剩余额度。
## What Changes
- 两个现有配额别名始终返回日/月 limit、used、remaining 和 resets_at。
- 无限额度 remaining 为 null；有限额度剩余不小于零。
- 验证用户隔离和 UTC 自然日/月边界。
## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/llm-call-metrics`: 补齐配额查询字段与无限额度语义。
## Impact
修改 api/auth/store.py 响应组装及相关 HTTP 测试；复用现有接口、配置、数据库。
