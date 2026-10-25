## ADDED Requirements

### Requirement: 预算与预警管理

用户 SHALL 能查看与编辑预算（全局上限、按难度分配、超限动作 pause/downgrade）、查看使用量，并管理预警规则（阈值百分比、通知渠道、启停）。规则保存 SHALL 与后端 schema 对齐（threshold 1–100、channel 白名单）；界面 SHALL 明示通知投递后端未实现（渠道仅存储）。

#### Scenario: 预算编辑生效

- **WHEN** 用户修改全局上限或难度分配并保存
- **THEN** 使用量与上限展示随之更新，非法输入被本地拒绝

#### Scenario: 预警规则管理

- **WHEN** 用户新增/启停/删除预警规则
- **THEN** 列表反映最新状态，且界面标注投递未实现
