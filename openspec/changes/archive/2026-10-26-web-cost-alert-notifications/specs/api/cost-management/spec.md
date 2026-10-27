## MODIFIED Requirements

### Requirement: 预警规则与触发历史

系统 SHALL 支持预警规则的创建/更新/删除/列表（threshold_pct、channel、target），非法通道与越界阈值 SHALL 被拒绝；响应中的 webhook/邮件目标 SHALL 脱敏；触发历史 SHALL 从 alert_events 按 owner 返回。

#### Scenario: 非法规则被拒绝

- **WHEN** 提交 threshold_pct 为 0 或 channel 为未知值的规则
- **THEN** 返回 400 且不落库

#### Scenario: 目标脱敏

- **WHEN** 列出包含 webhook URL 的规则
- **THEN** 响应仅含脱敏后的目标（保留协议与主机）


系统 SHALL 在 Web 评估开始及单元成本提交后按 owner 检查启用规则，以个人全局预算和已知累计成本触发 Slack、HTTPS Webhook、SMTP 或 log。成功投递 SHALL 写入现有历史；同一规则、阈值与上限的成功通知 SHALL 在后续单元及任务恢复时去重。失败 SHALL 有界重试且脱敏，不阻断评估或预算动作；下一次 worker 恢复允许重试。

#### Scenario: Web 规则真实发送
- **WHEN** 用户保存启用的 Slack、Webhook 或邮件规则且累计已知成本达到阈值（含 100%）
- **THEN** worker 向规则目标发送预算摘要并记录该用户成功历史

#### Scenario: 恢复去重与失败隔离
- **WHEN** 成功规则再次达到相同上限阈值或 worker 恢复，另一个渠道发送失败
- **THEN** 成功规则不重复发送，失败不影响其他规则、评估结果或预算暂停，恢复时可重试失败规则

#### Scenario: 未启用和其他用户规则
- **WHEN** 规则禁用、属于其他用户、无个人全局预算或尚未达到阈值
- **THEN** 不发送该规则且不产生成功历史
