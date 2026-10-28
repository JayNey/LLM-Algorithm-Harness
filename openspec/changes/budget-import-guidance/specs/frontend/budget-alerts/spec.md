## MODIFIED Requirements

### Requirement: 预算与预警管理

用户 SHALL 能查看与编辑预算（全局上限、按难度分配、超限动作 pause/downgrade）、查看使用量，并管理预警规则（阈值百分比、通知渠道、启停）。规则保存 SHALL 与后端 schema 对齐（threshold 1–100、channel 白名单）。界面 SHALL 说明 Slack/Webhook 使用规则中配置的目标，邮件投递依赖 worker 的 SMTP 配置；只有存在个人全局预算、启用规则且 Web 评估 worker 在成本检查边界触发时才会尝试投递。保存规则或预算不代表投递成功，没有运行中的评估时不会后台轮询。界面 MUST NOT 暗示所有业务任务都会触发预警；站内通知 SHALL 明确标注为 Mock。

#### Scenario: 预算编辑生效

- **WHEN** 用户修改全局上限或难度分配并保存
- **THEN** 使用量与上限展示随之更新，非法输入被本地拒绝

#### Scenario: 预警规则管理

- **WHEN** 用户新增/启停/删除预警规则
- **THEN** 列表反映最新状态，且界面准确说明规则所用渠道及投递触发条件

#### Scenario: 规则保存不等于成功投递

- **WHEN** 用户保存启用规则，但没有个人全局预算、运行中的 Web 评估或可用 worker 配置
- **THEN** 界面不声称通知已发送，并说明投递可能尚未触发或失败

#### Scenario: 邮件渠道依赖 SMTP worker 配置

- **WHEN** 用户选择邮件渠道
- **THEN** 界面说明收件人来自规则目标，SMTP 主机与认证配置必须由部署环境提供给 worker

#### Scenario: 站内通知保持 Mock

- **WHEN** 用户查看预算预警页或站内通知中心
- **THEN** 页面区分真实的外部预警投递与仍为 Mock 的站内通知，不把二者描述为同一能力
