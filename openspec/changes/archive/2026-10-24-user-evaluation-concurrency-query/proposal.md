## Why
用户已受评估并发准入限制，但现有配额接口无法查询已用与剩余名额。

## What Changes
- 在既有 `/quotas` 与 `/quotas/usage` 响应增加 `evaluation_concurrency`，包含 limit、used、remaining。
- 使用准入相同配置与持久化任务计数，更新文档与回归。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `api/evaluation-execution`：补齐现有用户评估并发额度的只读查询。

## Impact
仅现有监控服务、接口示例、文档及测试；无新端点、数据库迁移或准入行为变更。
