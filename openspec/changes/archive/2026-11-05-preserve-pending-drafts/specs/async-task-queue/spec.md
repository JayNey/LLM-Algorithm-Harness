## ADDED Requirements

### Requirement: 启动恢复保留未提交草稿
系统 SHALL 在 API 服务重建或共享库第二实例启动时保留未提交的 pending 评估和实验草稿，不改变其配置、状态、错误或时间；草稿 SHALL 可以通过实际启动入口唯一入队。无 started_at 且无关联或所属用户同类型同实体任务历史的 pending 记录 SHALL 视为草稿。存在开始时间、关联或任务历史的记录 SHALL 视为已提交执行；无活跃任务的孤立执行 SHALL 继续按现有策略标为 failed。pending/running/paused 活跃任务 SHALL 受到保护，业务暂停及终态 SHALL 不变。恢复 SHALL 幂等，且 SHALL NOT 覆盖并发创建、提交或完成后的有效状态。

#### Scenario: 草稿跨服务实例保持可启动
- **WHEN** 用户创建评估或实验但未启动，服务重建或第二实例启动并重复恢复
- **THEN** 草稿仍 pending，配置与时间不变，实际 start 只创建并发布一次任务

#### Scenario: 真正孤立执行仍然失败
- **WHEN** 记录为 running，或 pending 且已有开始时间、关联或所属用户同类型任务历史，并且没有活跃关联任务
- **THEN** 恢复将其标为 failed 并保存重启原因

#### Scenario: 活跃任务和终态保护
- **WHEN** pending/running 业务记录有活跃 pending/running/paused 任务，或业务记录已暂停或进入终态
- **THEN** 恢复不修改记录及任务

#### Scenario: 恢复与生命周期操作竞争
- **WHEN** 恢复期间并发创建草稿、启动入队或完成执行
- **THEN** 恢复按更新时数据库事实判断，不覆盖草稿、活跃任务或终态
