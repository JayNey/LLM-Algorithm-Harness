## ADDED Requirements

### Requirement: 多业务任务可安全恢复

系统 SHALL 允许所有者恢复已确认停止且为 paused 的 experiment、benchmark、import 和 ab_test 任务，保留同一 AsyncTask、业务实体、历史进度与检查点。实验以组合、基准以策略/题目、A/B 以变体/题目、导入以已校验条目为持久化单元；已落盘单元 SHALL 跳过，未落盘的中断单元可重试。已保存结果及费用 SHALL 不重复累计。

#### Scenario: 四类任务完成暂停恢复循环
- **WHEN** 四类运行任务被暂停，当前单元已落盘且 Worker 确认停止，所有者恢复
- **THEN** 任务与业务记录先同步 pending 再发布新消息，执行保留的剩余单元后均成为 completed，标识与历史结果不变

#### Scenario: 暂停尚未确认
- **WHEN** 当前 Worker 仍在完成并持久化中断边界的单元
- **THEN** 恢复被拒绝，不产生并行执行；Worker 退出后可恢复

#### Scenario: 重复恢复与旧执行
- **WHEN** 同一任务并发恢复、消息重复投递或旧执行回调到达
- **THEN** 最多一条有效执行，旧消息及回调不覆盖当前状态、结果和进度

#### Scenario: 所有权与终态
- **WHEN** 用户恢复他人、非 paused、业务终态或失效关联任务
- **THEN** 拒绝恢复，不发布消息、不改变业务记录；取消与恢复竞争按原子状态决定，取消后不能再执行

#### Scenario: 发布失败
- **WHEN** 恢复消息发布失败且同代任务仍 pending
- **THEN** 任务及业务记录或导入 job 成为 failed，保存错误；已开始、已取消、已结束或另一执行代际不被覆盖

## MODIFIED Requirements

### Requirement: 暂停的评估任务可以恢复

系统 SHALL 通过任务恢复接口接受调用方对自己名下、状态为 paused 的评估任务的恢复请求。恢复 SHALL 沿用原任务标识，保持关联评估指向同一任务，在发布队列消息之前将任务与评估原子写为 pending。非暂停、不属于调用方、关联失效或业务已终结的任务 SHALL 被拒绝，不发布消息、不修改原记录。experiment、benchmark、import、ab_test 的恢复 SHALL 遵循多业务任务安全恢复要求，未知类型 SHALL 被拒绝。评估现有容量限制与检查点续跑 SHALL 保留。

#### Scenario: 恢复暂停的评估任务
- **WHEN** 调用方恢复自己的 paused 评估
- **THEN** 保留原任务关联并先落库 pending 后发布，原有检查点继续使用

#### Scenario: 拒绝非法恢复
- **WHEN** 恢复非暂停、他人、未知类型、关联失效或业务终态任务
- **THEN** 拒绝恢复且不发布消息

#### Scenario: 拒绝恢复非暂停任务
- **WHEN** 调用方恢复属于自己但状态不是 paused 的任务
- **THEN** 拒绝请求，保持原记录且不发布消息

#### Scenario: 拒绝恢复非评估任务
- **WHEN** 调用方恢复自己的 paused 非评估任务
- **THEN** experiment、benchmark、import、ab_test 按多业务安全恢复要求处理；其余未知类型拒绝请求，保持原记录且不发布消息

#### Scenario: 拒绝恢复他人的任务
- **WHEN** 调用方恢复不属于自己的暂停任务
- **THEN** 拒绝请求且不发布消息
