## ADDED Requirements

### Requirement: 评估删除的活动任务保护

系统 SHALL 仅允许删除业务状态为 pending、completed 或 cancelled 且不存在同一所有者的 pending/running/paused 关联评估任务的记录。活动任务存在时 SHALL 拒绝删除、提示先取消并等待停止，并保留业务记录、任务、结果和文件。列表、详情和异步评估响应的 `can_delete` SHALL 反映上述持久化状态条件，且不轮询 broker。

#### Scenario: 已入队 pending 评估拒绝删除

- **WHEN** 评估成功入队且关联任务为 pending，用户请求删除
- **THEN** 请求以 HTTP 400 拒绝，`can_delete` 为 false，评估、任务及其额度占用保留，文件清理未执行

#### Scenario: 活动任务优先于可删除业务状态

- **WHEN** pending、completed 或 cancelled 评估仍有 pending/running/paused 的关联评估任务
- **THEN** 所有评估响应均投影 `can_delete=false`，删除不得移除任何业务数据或文件

#### Scenario: 取消停止后删除与额度释放

- **WHEN** 评估取消已提交且在途执行已经停止，用户删除该评估
- **THEN** 删除成功，评估、结果及文件按现有规则清理，没有遗留 pending/running/paused 关联任务占用额度或可继续执行

### Requirement: 评估删除与提交互斥

系统 SHALL 使评估删除与提交在同一事务互斥边界内判定是否可执行，并在删除的活动任务校验、文件清理和业务记录移除完成前保持该保护。执行尚未停止时 SHALL 拒绝清理；清理失败 SHALL 保留评估记录以便重试。所有服务层删除入口 SHALL 遵守相同保护。

#### Scenario: 提交先于删除取得互斥权

- **WHEN** 同一评估的提交和删除并发，提交先完成入队
- **THEN** 删除重新检查已提交任务并拒绝，不移除文件或业务记录

#### Scenario: 删除先于提交取得互斥权

- **WHEN** 草稿删除先取得互斥权，提交在清理期间尝试启动该评估
- **THEN** 删除完成后提交被拒绝，不发布任务消息、不遗留活动 AsyncTask

#### Scenario: 取消后仍有在途执行

- **WHEN** 任务已标记 cancelled 但原执行者尚未释放执行权，用户请求删除
- **THEN** 删除被拒绝且不清理文件、结果或业务记录，执行停止后允许重试

#### Scenario: 清理失败可重试

- **WHEN** 可删除评估的文件清理回调抛出异常
- **THEN** 评估记录不被删除，事务锁释放，后续可重新请求删除
