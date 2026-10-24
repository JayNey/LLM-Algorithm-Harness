## Why
现有监控已汇总共享数据库中的缓存快照，但缺少请求量不均的多 Worker 验收，文档仍把该功能列为待完成。

## What Changes
- 明确整体命中率公式与保留样本边界。
- 补充跨进程、重复上报、零请求和过期退出的验证。
- 更新监控指南及过时待办。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `llm-response-cache`: 明确实际缓存监控的跨 Worker 加权命中率。

## Impact
沿用现有快照聚合和管理员接口，以测试及文档补齐为主，必要时最小调整实现；无新增接口、依赖或数据库 schema。
