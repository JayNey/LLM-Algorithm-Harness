## ADDED Requirements

### Requirement: 评估可以作为异步任务执行

系统 SHALL 通过评估启动接口接受一次处于 `pending` 的已有评估的异步执行请求，立即返回任务标识，且评估记录保持 `pending`，直到 worker 开始执行。入队 SHALL 在提交 Celery 消息之前先把任务记录与其到评估的关联落库，使 worker 能可靠解析到关联任务。执行期间状态 SHALL 保持在 `pending`、`running`、`paused`、`completed`、`failed` 或 `cancelled` 之一。任务完成后评估记录 SHALL 反映最终状态；失败时 SHALL 保存错误信息。取消一个已入队评估 SHALL revoke 对应 Celery 任务并把状态置为 `cancelled`。API 进程重启 SHALL NOT 把已经入队的 `pending` 评估标成失败。

#### Scenario: 成功提交评估任务

- **WHEN** 调用方对一个处于 `pending` 的已有评估调用评估启动接口
- **THEN** 系统返回任务标识，评估记录仍为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 入队先落库后发布

- **WHEN** 评估启动接口提交异步执行
- **THEN** 任务记录与其到评估的关联在 Celery 消息发布之前已落库，worker 能解析到该关联任务

#### Scenario: 取消已入队评估

- **WHEN** 调用方取消一个仍处于 `pending` 或 `running` 的评估
- **THEN** 系统 revoke 对应 Celery 任务，评估与任务状态变为 `cancelled`

#### Scenario: 重启保留已入队评估

- **WHEN** 评估已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 评估记录仍为 `pending`，且其任务标识仍然有效
