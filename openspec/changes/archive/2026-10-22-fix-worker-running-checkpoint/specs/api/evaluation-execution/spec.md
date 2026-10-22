## MODIFIED Requirements

### Requirement: 恢复继续不重复已完成单元

系统 SHALL 支持对处于 `paused` 或 `failed` 的评估重新发起执行，从尚未完成的单元继续；worker 丢失后重投递的评估若遗留 `running` 检查点，SHALL 同样从检查点恢复并重新排队中断的单元。已经写入结果的单元 SHALL NOT 被重复执行或产生重复结果记录，累计花费与计数 SHALL 在既有基础上继续而非从头重置。恢复 SHALL 校验既有配置和数据指纹。

#### Scenario: 暂停后恢复继续剩余单元

- **WHEN** 一个因预算触顶而 `paused` 的评估在提高预算后被重新发起执行
- **THEN** 仅剩余未完成的单元被执行，已完成单元的结果记录不重复，`completed_count` 从暂停时的值继续增长

#### Scenario: worker 丢失后从 running 检查点恢复

- **WHEN** worker 丢失后任务被重投递，检查点为 `running` 且包含已完成、执行中和排队单元
- **THEN** 系统保留已完成单元，只重跑中断与排队单元，结果不重复、费用继续累计，任务与评估反映最终状态

#### Scenario: running 检查点指纹不匹配

- **WHEN** 重投递评估的既有 `running` 检查点与当前配置或数据指纹不一致
- **THEN** 系统拒绝恢复，不执行新单元、不覆盖检查点
