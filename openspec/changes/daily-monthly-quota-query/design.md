## Context
AuthStore.user_api_calls 已读取当前用户 UTC 日/月计量，MonitoringService 将结果返回两个已认证别名。无限额度缺少 remaining。
## Goals / Non-Goals
统一查询字段，不修改准入、数据库、配置和前端。
## Decisions
基础周期响应添加 remaining: null，有限额度继续覆盖为 max(limit-used,0)。resets_at 保持 UTC ISO 8601 格式，分别为次日零点和下月一日零点。
## Risks / Trade-offs
以 HTTP 测试覆盖无限、有限、零、超限和混合配置，及跨日/月/年、闰年和当前用户隔离。
## Migration Plan
无需迁移；兼容增加可空字段。
## Open Questions
无。
