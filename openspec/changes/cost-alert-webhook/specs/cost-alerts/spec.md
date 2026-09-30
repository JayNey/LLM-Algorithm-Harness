# cost-alerts Specification

## ADDED Requirements

### Requirement: 运行级成本阈值预警

系统 SHALL 在配置正数 `budget_cap_usd` 后按当前任务的已知累计成本判断预警阈值。默认阈值 SHALL 为 50%、80%、90%，用户 SHALL 能配置不重复的 1–99 整数百分比。一次成本结算跨越多个阈值时 SHALL 为每个阈值记录触发；未知定价或 usage 的成本 SHALL 标注为未知且不得视为零成本计入百分比。

#### Scenario: 跨越多个阈值

- **WHEN** 预算为 10 美元，已知累计成本从 4 美元增长到 9 美元
- **THEN** 50%、80%、90% 阈值各处理一次，对每个配置渠道保存发送结果

#### Scenario: 成本未知

- **WHEN** 某次模型调用缺少定价或 usage
- **THEN** 该调用不增加已知成本，未知计数增加，报告和通知明确显示成本有未知部分

### Requirement: 多渠道通知与安全失败记录

系统 SHALL 支持 Slack Incoming Webhook、通用 HTTPS JSON Webhook 和 SMTP 邮件。每个阈值与渠道在同一任务内成功发送后 SHALL 不再发送，包括 `--resume`；发送 SHALL 有可配置的超时与有限重试。独立的 `output_dir/tasks/<run_id>.cost-alerts.json` SHALL 持久化成功渠道，以及失败渠道的最终尝试次数和错误类别；它不要求逐次尝试历史。发送失败 SHALL 不阻止评测或预算暂停。Webhook URL、SMTP 凭据和模型密钥 SHALL 不进入通知内容、日志、任务记录或报告。

#### Scenario: Webhook 发送

- **WHEN** 已知成本跨越 80% 且配置通用 Webhook
- **THEN** 发送 HTTPS JSON，包含事件、任务 ID、阈值、预算、已知累计成本、已知预算百分比、未知计数和成本口径，并保存发送结果

#### Scenario: 发送失败与恢复

- **WHEN** 某渠道请求连续超时直到重试用尽，随后用户恢复同一任务
- **THEN** 原失败及尝试次数可查询；已经成功的其他渠道不重复发送，凭据不出现在错误记录中

### Requirement: 显式超预算自动暂停

系统 SHALL 支持 `--auto-stop-on-budget`（或配置文件等价字段）。该模式 SHALL 以一个工作线程执行，并在每个题目结算后检查已知累计成本。达到预算上限时，任务 SHALL 停止派发尚未开始的单元，并持久化 `paused` 状态与暂停事件；该模式 SHALL 可用于普通运行和成本敏感选择器运行。系统 SHALL 不得把未派发单元记为已完成。单次题目可能跨过上限，报告 SHALL 如实呈现。

#### Scenario: 到达预算上限

- **WHEN** 自动暂停模式下已知累计成本达到预算且仍有 queued 单元
- **THEN** 不再派发 queued 单元，任务保持 paused，queued 数量和最终累计成本可查询

#### Scenario: 恢复已达上限的任务

- **WHEN** 使用相同配置及数据集恢复已达到预算的 paused 任务
- **THEN** 已完成成本先回放，不派发新单元，已成功阈值通知不重复发送

### Requirement: 截断报告与成本控制摘要

系统 SHALL 在 `summary.json.cost_control` 中保存预算、已知累计成本、未知计数、降级题目数、预算动作与 `incomplete` 标记。任务状态 SHALL 保存在 `metadata.json.task.state`，通知结果 SHALL 保存在独立预警状态文件。自动暂停时 SHALL 在运行输出目录保存 `cost_cutoff.json`，列出任务 ID、暂停时间、预算、已知累计成本、未知计数、已完成与排队单元数量，并明确结果为截断结果。

#### Scenario: 暂停后查看结果

- **WHEN** 自动暂停后运行输出写盘
- **THEN** `summary.json.cost_control.incomplete` 为 true，`metadata.json.task.state` 为 paused，`cost_cutoff.json` 存在且其已完成/排队数量与任务记录一致

### Requirement: 配置边界与兼容

系统 SHALL 在启动前拒绝无预算的预警或预算动作，以及同时指定自动暂停与降级动作。显式降级 SHALL 要求难度策略映射；未显式指定动作的选择器预算运行 SHALL 保持原有降级行为。无预算配置的既有 CLI 运行和固定预算实验 SHALL 保持原有执行语义。

#### Scenario: 保持原有降级

- **WHEN** 运行使用难度策略映射与预算上限，但没有指定预算动作
- **THEN** 达到上限后的后续题目按既有规则改用最便宜的映射策略

#### Scenario: 不合法的预算组合

- **WHEN** 指定预警阈值但没有预算，或同时指定自动暂停与降级
- **THEN** 在任何模型调用前报错退出
