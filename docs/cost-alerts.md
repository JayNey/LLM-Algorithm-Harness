# 成本预警与预算暂停

`harness run` 可以按本次任务的已知模型调用成本发送预算预警。设置预算上限后，默认在 50%、80%、90% 触发；也可以指定阈值、通知渠道，并选择达到预算后的动作。

## 快速开始

自动暂停适合需要人工检查剩余预算的运行：

```bash
harness run --config config.local.yaml \
  --budget-cap 5 \
  --auto-stop-on-budget \
  --cost-alert-thresholds 50,80,90 \
  --run-id budget-trial-01
```

命令行参数可覆盖配置文件中的预算、动作和阈值。`--budget-cap` 的单位是美元，必须大于零。预警阈值是 1–99 的不重复整数百分比，用逗号分隔；未指定时使用 50、80、90。启用预警或预算动作都需要预算上限。

## 通知渠道

在现有评测配置中增加以下配置片段。示例地址和密码必须在本地配置文件中替换为真实值；配置加载器不会自动展开这些字段中的 `${ENV_VAR}` 文本。按需保留一个或多个渠道：

```yaml
budget_cap_usd: 5
budget_action: auto_stop
cost_alerts:
  thresholds: [50, 80, 90]
  slack_webhook_url: "https://hooks.slack.com/services/REPLACE_LOCALLY"
  webhook_url: "https://example.com/replace-with-your-endpoint"
  smtp_host: "smtp.example.com"
  smtp_port: 587
  smtp_username: "notifier@example.com"
  smtp_password: "REPLACE_LOCALLY"
  smtp_from: "notifier@example.com"
  smtp_to: ["owner@example.com"]
  smtp_use_starttls: true
  timeout_seconds: 5
  max_retries: 2
```

- **Slack**：填写 Slack Incoming Webhook 的 HTTPS URL。系统发送包含任务、阈值与成本摘要的 JSON `text` 消息。
- **通用 Webhook**：填写 HTTPS URL。系统发送 JSON，包含 `event`、`run_id`、`threshold_percent`、`budget_cap_usd`、`accumulated_cost_usd`、`known_budget_percent`、`unknown_usage_results` 和 `cost_basis`。当前请求体不带时间戳。接收方可用任务 ID、阈值和渠道组合去重。
- **SMTP 邮件**：至少填写 `smtp_host`、`smtp_from` 和 `smtp_to`。需要认证时填写用户名和密码；默认使用 STARTTLS。邮件正文包含同样的预算摘要。

Webhook URL 与 SMTP 密码可能是凭据。把含真实值的配置文件保存在本地私有位置，不要提交到仓库。结果中的配置快照会脱敏；预警状态只保存阈值、渠道、发送成功状态，以及失败时的尝试次数和错误类别，不保存这些凭据。

每次通知有超时限制，失败时最多再重试 `max_retries` 次。默认设置是每次 5 秒、额外重试 2 次。网络或服务器暂时故障可能重试；发送失败会写入脱敏记录，不会让评测失败，也不会阻止预算暂停。已成功发送的阈值与渠道在同一任务恢复后不会再发送。远端接收成功、但进程在本地成功记录写盘前退出时，恢复可能重复发送；接收方应自行去重。

## 达到预算后的动作

### 自动暂停

`--auto-stop-on-budget` 或配置中的 `budget_action: auto_stop` 可以用于普通评测，也可以用于难度策略选择器。该模式固定使用一个工作线程，即使配置了更高的 `max_workers`。已知累计成本达到预算时，当前题目已经结算，系统停止派发新题。任务状态成为 `paused`；尚未开始的题目保持 queued。暂停不是失败或取消。

预算按每道题结束后的实际已知成本检查。单道题可能跨过预算线，未知价格的调用也无法纳入已知金额，因此上限并非严格的账单封顶。`--resume --run-id budget-trial-01` 会先回放已完成题目的成本；如果相同预算已经达到，它仍不会派发新题。要使用更高预算完成剩余题目，需要建立新的任务配置和运行计划，不能通过修改配置绕过同一任务的恢复指纹校验。

### 策略降级

已有的难度策略选择器配合 `--budget-cap` 时，默认继续使用降级：到达预算后，后续题目改用映射中最便宜的策略。`--downgrade-on-budget` 可显式指定这个动作，且必须有 `--difficulty-strategy` 映射。两个动作参数互斥。

```bash
harness run --config config.local.yaml \
  --difficulty-strategy easy=vanilla medium=chain_of_thought hard=multi_round_feedback \
  --budget-cap 5 \
  --downgrade-on-budget
```

## 成本口径与结果文件

运行级预算只累计模型 trace 中同时具有定价和 usage 的调用成本。缺少其中任一项时，成本是**未知**，不计入已知金额或阈值百分比；任务摘要和通知会显示未知计数。累计金额是估算，不等同于服务商最终账单。

任务状态及暂停事件保存在 `output_dir/tasks/<run_id>.json`。预警的成功渠道和失败渠道的尝试次数、错误类别保存在独立的 `output_dir/tasks/<run_id>.cost-alerts.json`；其中没有逐次尝试的历史。运行结果保存在 `output_dir/<run_id>/`：

- `summary.json` 的 `cost_control` 包含预算、已知成本、未知计数、降级题目数、预算动作和 `incomplete` 标记；通知结果在上述预警状态文件中，任务状态在 `metadata.json.task.state` 中。
- 自动暂停时的 `cost_cutoff.json` 包含暂停时间、预算、成本以及已完成和仍排队的单元数；这是截断报告。
- 各策略详细结果文件给尚未运行的题目写入 `cancelled` 占位记录；聚合报告的分母只包含已执行单元。查看通过率时应先检查任务是否为 `paused`，并结合截止报告查看原题集覆盖范围。

通知与自动暂停仅适用于 `harness run` 的运行级预算；`harness experiment` 的逐题预算规则不受影响。
