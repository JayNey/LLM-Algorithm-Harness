## Why

设置美元上限的 CLI 和 Web 评估可能在缺价或缺用量后继续派发。已知金额可能仍是零，导致用户误判预算和费用。

## What Changes

- 在有美元上限的评估中，开始前发现缺价时暂停，执行中发现未知费用时阻止后续请求和派发。
- 保留已知费用小计和未知单元数，公开预算状态并区分真实零价与金额未知。
- 在重试和恢复时复用既有检查点与结果记录，避免重复累计。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `cost-aware-strategy-selection` 补充 CLI 美元预算与未知费用规则。
- `api/cost-management` 补充 Web 评估自身美元预算的派发和恢复规则。
- `frontend/app-shell` 补充 Web 评估详情的费用与预算状态。

## Impact

影响 CLI 评估、Web 评估 worker、任务响应和详情摘要。关联 GitHub #481。
