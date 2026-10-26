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

## Web 预警规则与运行期通知

Web「预算与预警」中保存的启用规则在 Celery 评估 worker 启动（含恢复）和每个单元成本提交后生效。先保存**个人全局预算**，再选择渠道、阈值（1–100%）和目标。规则使用当前用户全部评估已知累计成本及已完成基准运行成本，与个人预算执行口径一致；不是单任务预算，也不是按月重置的额度。未知用量不视作免费，通知单独列出已持久化评估结果中的未知计数。没有个人全局预算时不发通知，只有难度预算时也不触发全局规则。

- Slack / Webhook：目标填完整 HTTPS URL，不含内嵌用户名或密码；Slack 使用 Incoming Webhook。Web 通道不跟随重定向，3xx 视为失败。通用 Webhook 的 JSON 增加 `rule_id`，`cost_basis` 为 `owner_known_pricing_usage`，`run_id` 是本次触发检查的 Web 评估 ID。
- 邮件（SMTP）：规则目标填一个收件邮箱。SMTP 连接由 worker 的环境或 `.env` 提供，例如：

```dotenv
COST_ALERT_SMTP_HOST=smtp.example.com
COST_ALERT_SMTP_PORT=587
COST_ALERT_SMTP_FROM=notifier@example.com
COST_ALERT_SMTP_USERNAME=notifier@example.com
COST_ALERT_SMTP_PASSWORD=REPLACE_LOCALLY
COST_ALERT_SMTP_USE_STARTTLS=true
```

无认证 SMTP 可以省略用户名和密码。认证必须使用 STARTTLS。修改环境后重启 worker；缺失或无效连接配置会产生脱敏失败日志，不会伪造成功通知。

每次投递最多尝试 3 次，每次超时 5 秒；暂时性错误重试。每个 worker 执行实例对同一规则、阈值和预算上限只进行一组尝试，失败可在任务恢复后重试。失败不阻断其他规则，也不改变评估结果、预算暂停或降级。

成功（或 log 渠道的本地触发）写入「预警历史」；失败仅记录不含目标或凭据的日志。相同规则、阈值、上限在后续单元、其他任务及恢复时不重复成功通知。更改上限或阈值后可再次通知；仅修改目标不重发，需重新创建规则。每次检查重新读取启用状态，禁用后不再投递。并发 worker 通过短事务占用投递记录，网络发送期间不持有数据库写锁。在途记录不显示为成功历史；进程中断后的记录保留 5 分钟，到期后由后续评估边界重试（无后台轮询，可能需稍后恢复）。发送超过租期仍可能重复；远端已接收而本地提交前进程退出时仍可能重复，Webhook 接收方可按 `rule_id`、`threshold_percent`、`budget_cap_usd` 去重。

当前通知由 Web 评估的执行边界触发；仅保存规则或预算不会立即发送，没有运行中的评估时也不进行后台轮询。CLI 配置与 Web 规则分别生效。
