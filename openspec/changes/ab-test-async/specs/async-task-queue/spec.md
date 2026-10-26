## ADDED Requirements
### Requirement: A/B 测试可以作为异步任务执行
系统 SHALL 通过现有 A/B 运行接口为自己的 pending 测试创建唯一关联 AsyncTask（ab_test），先提交任务记录再发布到 Celery default 队列，立即返回 task_id；worker 开始前测试 SHALL 保持 pending。worker SHALL 验证所有者并在内部解析密钥；完成或失败时两层状态、时间和错误 SHALL 一致。API 重启 SHALL 保留未启动配置和活跃异步测试。暂停或取消 SHALL 同步业务状态，worker SHALL 在下一题边界停止派发，收尾不得覆盖停止状态。重复启动 SHALL 被拒绝，重复投递 SHALL 不重复执行或改变已有状态。监控和执行日志 SHALL 识别 A/B 类型。

#### Scenario: 先落库后发布并可查询
- **WHEN** 用户启动自己的 pending 测试
- **THEN** 消息发布前任务已落库，响应和详情含相同 task_id，测试在 worker 开始前为 pending。

#### Scenario: 发布失败
- **WHEN** broker 发布失败
- **THEN** 仍为 pending 的任务和测试均为 failed，保存错误和完成时间；并发已开始、取消或完成的状态不被覆盖。

#### Scenario: 并发启动和重复投递
- **WHEN** 同一测试被重复或并发启动，或消息被重复投递
- **THEN** 最多创建并执行一个任务，重复消息不覆盖已有状态。

#### Scenario: 成功与失败
- **WHEN** worker 执行成功或发生异常
- **THEN** 两层均为 completed 或 failed，并持久化时间，成功可读取报告，失败可读取原因。

#### Scenario: 用户隔离
- **WHEN** 用户启动他人测试或 worker 收到不匹配所有者
- **THEN** 不运行测试，不泄露他人密钥或修改他人业务记录。

#### Scenario: 重启保护
- **WHEN** API 在配置未启动、已排队或 worker 运行时重启
- **THEN** 保持原状态和任务关联，worker 后续可正常完成并读取结果。

#### Scenario: 暂停与取消
- **WHEN** 用户暂停或取消尚未结束的 A/B 任务
- **THEN** 业务和任务状态同步，取消会 revoke，runner 不开始后续题目，收尾不覆盖 paused/cancelled。

#### Scenario: 监控与日志
- **WHEN** A/B worker 运行并结束
- **THEN** 监控将类型显示为 ab_test，生命周期事件沿用现有所有者隔离日志。

#### Scenario: worker 子进程丢失
- **WHEN** Celery 父进程确认执行 A/B 的子进程丢失
- **THEN** 未结束的任务和业务记录变为 failed，保存完成时间；消息不重新派发，已暂停或取消的状态不被覆盖。
