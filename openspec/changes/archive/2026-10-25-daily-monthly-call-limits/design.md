## 实现
AuthSettings 提供 USER_DAILY_API_CALL_LIMIT / USER_MONTHLY_API_CALL_LIMIT，可空、非负整数。沿用 UTC 自然日/月。
无限时保留完成后 best-effort 计量。任一限制启用时绑定私有预调用钩子，在每次 SDK 尝试前使用 BEGIN IMMEDIATE 检查两周期并原子递增；任一耗尽则全部不写。失败及重试各占一次，按准入时间归属周期，跨进程共享认证数据库。
钩子在重试捕获及耗时测量外执行；超额为 QUOTA_EXCEEDED（429），带周期及 Retry-After；数据库故障 fail closed 为 503。被拒绝调用不计入 SDK 监控。私有回调不序列化。
额度视图启用时返回 enforced、limit、remaining 和 atomic_before_sdk_attempt 语义。缓存、列表、连接验证、无用户 CLI 不耗额度。
## 验证
覆盖独立限额、零/无限、并发、重试失败、周期边界、重启、存储故障和额度视图；回归现有监控与认证测试。
