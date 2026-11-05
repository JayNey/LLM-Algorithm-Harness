## Why

修复 #350：provider 异常绕过调用记账，允许继续尝试的策略可超过 max_calls。

## What Changes

- 准入时扣除逻辑调用名额，响应仅结算 token。
- Self-Consistency 预算耗尽时停止并保留已完成候选与明确终态。
- 明确缓存与 SDK 重试口径，增加离线回归。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `experiment/budget-comparison`：每题调用预算包含失败与缓存命中的逻辑调用。

## Impact

仅预算包装器、Self-Consistency、预算模型字段说明、实验指南与测试；无外部 API 或依赖变化。
