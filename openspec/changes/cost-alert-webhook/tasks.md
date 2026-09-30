# Tasks: cost-alert-webhook

## 1. 配置、CLI 与校验

- [x] 增加 `CostAlertConfig`、`budget_action` 与安全配置快照；校验预算、阈值、渠道必填字段和 HTTPS Webhook。
- [x] 增加 `--cost-alert-thresholds`、`--auto-stop-on-budget`、`--downgrade-on-budget`；保持选择器 + 预算的默认降级语义。
- [x] 定向测试覆盖无预算预警、动作互斥、错误阈值及原有 CLI 路径。

## 2. 运行成本与通知

- [x] 在普通与选择器任务中按同一已知成本口径结算，标记未知 usage/定价；跨多个阈值分别触发。
- [x] 实现 Slack、通用 JSON Webhook 与 SMTP 发送，限制超时及重试；保存成功渠道和失败渠道的最终尝试次数、错误类别。
- [x] 定向测试覆盖 payload、阈值去重、恢复后去重、HTTP/SMTP 错误和密钥不泄露。

## 3. 自动暂停与报告

- [x] 任务服务支持 `paused`：自动暂停以单工作线程在题目结算后停止派发，保留 queued 单元和有序事件。
- [x] 生成 `summary.json.cost_control`；暂停时生成 `cost_cutoff.json`，并明确结果为截断结果。
- [x] 定向测试覆盖单题越界、普通/选择器运行、恢复时已达上限及默认降级兼容。

## 4. 文档与验收

- [x] 更新 README 与 `docs/cost-alerts.md`，说明配置、CLI、通知格式、未知成本、单线程暂停和恢复限制。
- [x] 运行定向测试、相关回归、`openspec validate cost-alert-webhook --strict --no-interactive`，记录结果并完成独立审查。
