# Design: 成本预警、通知与超预算暂停

## 成本口径与触发

沿用 `RunCostMonitor` 的运行级台账：从每个已完成题目的 `llm_traces[].pricing_metadata.total_cost` 累加已知定价、已知 usage 的调用成本。缺少 usage 或定价的调用保持 `unknown`，单独计数，绝不以零美元代替。阈值按 `known_cost / budget_cap_usd × 100` 判断，成本在题目完成后结算。一次结算跨过多个阈值时逐个触发；同一任务的已成功阈值在恢复后不重发。

`budget_cap_usd` 为正数。`cost_alerts.thresholds` 默认为 `[50, 80, 90]`，自定义值为 1–99 的不重复整数百分比，按升序使用。没有预算时拒绝启用预警或预算动作；通知渠道可按需要组合。预算与阈值只作用于当前 `harness run`，不作用于 `experiment` 的逐题预算。

## 预算动作与并发

`budget_action` 为 `auto_stop` 或 `downgrade`。选择器 + 预算但未指定动作时沿用 `downgrade`；显式 `--downgrade-on-budget` 仍要求难度策略映射。`auto_stop` 可用于普通运行或选择器运行，并与降级互斥。

`auto_stop` 固定以一个工作线程执行，在每个题目结算后检查上限。达到上限后任务服务停止派发排队单元，留下尚未开始的单元为 queued，最终持久化 `paused` 状态和事件。暂停不是失败或用户取消，不应把未运行题目报成已解答。单次题目成本可能跨过上限，未知成本也无法纳入判断；不能承诺硬性不超支。

## 通知与持久化

通知以 `(run_id, threshold_percent, channel)` 识别。成功渠道和失败渠道的最终尝试次数、错误类别存入独立的 `output_dir/tasks/<run_id>.cost-alerts.json`，以临时文件、`fsync` 和原子替换写入。它不保存逐次尝试历史，也不把通知作为任务事件写入 `TaskRecord`。一次发送最多 `1 + max_retries` 次尝试，默认每次超时 5 秒、额外重试 2 次。HTTP 429/5xx、超时及连接错误可以重试；其他 HTTP 4xx 直接失败。SMTP 仅对短暂回复和连接故障重试，认证等永久错误直接失败。发送失败不能使评测失败或阻止暂停；恢复时跳过已成功的渠道，失败渠道可以再进行一次有限重试周期。

自定义 Webhook 使用 HTTPS POST JSON，正文包含 `event`, `run_id`, `threshold_percent`, `budget_cap_usd`, `accumulated_cost_usd`, `known_budget_percent`, `unknown_usage_results`, `cost_basis`；当前不包含时间戳。Slack 使用其 Incoming Webhook 的 JSON `text` 格式；SMTP 发送纯文本邮件。请求不携带模型提示词、代码、API Key 或配置快照。Webhook URL、SMTP 密码与认证字段视为凭据，日志和持久化内容只显示渠道名称及错误类别。任务指纹包含配置的安全快照及通知凭据指纹；原始密钥绝不保存。

外部发送与本地落盘无法组成一个事务。进程若恰好在远端接收成功后、本地成功记录落盘前退出，恢复时可能重发。接收方可以通过 `run_id + threshold_percent + channel` 去重。

## 报告与恢复

常规 `summary.json` 增加 `cost_control`：预算、已知累计成本、未知计数、降级题目数、预算动作与 `incomplete` 布尔值。通知成功/失败状态见独立预警状态文件，任务状态见 `metadata.json.task.state`。`auto_stop` 暂停时运行目录额外写 `cost_cutoff.json`，包含 `run_id`、暂停时间、预算、已知累计成本、未知计数、已完成和仍排队的单元数及状态。详细结果文件对未执行题目使用 `cancelled` 占位记录；聚合报告只计算已执行单元，未运行题目不计入失败率分母，并由 `incomplete` 和截断报告明确说明覆盖范围。

`--resume --run-id` 继续使用配置及数据集指纹校验，先回放已完成题目的成本，并加载独立预警状态文件。如果同一预算已达，自动暂停模式不再派发新单元，也不重复已成功的通知。已在途调用状态不确定时沿用任务服务原有恢复语义；不能声称外部调用或通知恰好执行一次。

## 验证重点

- 阈值边界、单次跨过多个阈值、并发结算、未知定价/usage、不重复成功通知。
- Slack、自定义 Webhook、SMTP 请求格式；超时、短暂/永久错误的重试次数和脱敏失败记录。
- 普通运行及选择器运行的单线程自动暂停，保留 queued 单元、产生截断报告；既有默认降级不回归。
- 恢复回放、配置/数据集指纹不匹配、已成功渠道不重发；无通知配置时正常完成。
