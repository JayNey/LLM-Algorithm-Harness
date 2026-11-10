## Why

[#445](https://github.com/JayNey/LLM-Algorithm-Harness/issues/445) 要求在待发布的 Web 构建上复验题库导入导出、通知持久化与预算预警，并提供脱敏证据。此前已有小文件导入证据和针对恢复、通知刷新竞态的修复。

## What Changes

- 从生产 Web 入口执行四项验收，记录候选版本、作业与通知标识摘要、HTTP 状态和界面结果。
- 对发现的可复现缺陷补齐回归验证并在修复后的候选上复验。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/problems-management` 保证访问 Cookie 到期时的题库导出。
- `frontend/budget-alerts` 展示外部投递成功与失败。
- `api/cost-management` 在既有历史保留脱敏的投递结果。

## Impact

验收涉及个人题库、Cookie 会话、通知和预算设置，使用隔离应用、账号、数据库、队列及外部渠道接收替身。
