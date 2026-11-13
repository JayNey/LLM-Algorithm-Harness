## Why

Web 评估的生成请求可能在 5 秒时失败，失败汇总也会漏掉已保存的迭代错误，导致用户难以判断故障原因。

## What Changes

- Web 评估创建时保存独立的模型生成超时，默认 60 秒，执行与恢复均使用保存值。
- 为可恢复的供应商错误启用有次数上限、受时间和预算约束的重试。
- 单题结果、失败案例和聚类显示模型生成或沙箱阶段的脱敏错误类型，并读取历史迭代记录。

## Capabilities

### Modified Capabilities

- `api/evaluation-execution` — 生成超时、重试及预算准入。
- `api/evaluation-results` — 失败阶段、错误类型和历史结果回显。

## Impact

涉及 Web 评估创建和 worker、供应商客户端、数据库迁移、结果 API 和页面。对应 GitHub #480，用户确认使用 Tweak 和独立分支。
