# async-task-queue Specification

## Purpose
让实验、题目导入和基准测试进入与评估任务相同的异步队列，使调用方可以拿到任务标识并查询状态、进度和失败原因。

## Requirements

### Requirement: 实验可以作为异步任务执行

系统 SHALL 通过实验运行接口接受一次处于 `pending` 的已有实验的异步执行请求，立即返回任务标识，且实验记录保持 `pending`，直到 worker 开始执行。执行期间状态 SHALL 保持在 `pending`、`running`、`completed`、`failed` 或 `cancelled` 之一。任务完成后，实验记录 SHALL 反映最终状态；失败时 SHALL 保存错误信息。API 进程重启 SHALL NOT 把已经入队的 `pending` 实验标成失败。

#### Scenario: 成功提交实验任务

- **WHEN** 调用方对一个处于 `pending` 的已有实验调用实验运行接口
- **THEN** 系统返回任务标识，实验记录仍为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 实验执行失败时留下错误

- **WHEN** 实验执行过程中发生业务错误或运行失败
- **THEN** 任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 重启保留已入队实验

- **WHEN** 实验已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 实验记录仍为 `pending`，且其任务标识仍然有效

### Requirement: 题目导入可以作为异步任务执行

系统 SHALL 通过题目导入接口接受一次已登记导入作业的异步执行请求，立即返回任务标识和作业标识。导入完成或失败后，任务状态 SHALL 与导入作业的最终结果一致。执行期间系统 SHALL 报告已处理数量与总数量。

#### Scenario: 成功提交导入任务

- **WHEN** 调用方通过题目导入接口提交一个属于自己的已上传文件
- **THEN** 系统返回任务标识和作业标识，且不在 API 进程内执行导入

#### Scenario: 查询导入进度

- **WHEN** 导入任务正在执行且已知总数量
- **THEN** 进度查询返回已处理数量、总数量，以及由二者算出的完成比例

#### Scenario: 导入对象不存在

- **WHEN** 调用方提交的导入作业不存在或不属于该调用方
- **THEN** 系统拒绝执行，且不把其他用户的导入数据写入数据集

### Requirement: 基准测试可以作为异步任务执行

系统 SHALL 通过基准运行接口创建一次基准运行并接受其异步执行请求，立即返回任务标识，且运行记录保持 `pending`，直到 worker 开始执行。结束后系统 SHALL 把准确率、成本与结果摘要写入该运行记录。失败时 SHALL 把运行标记为 `failed` 并保存错误信息。API 进程重启 SHALL NOT 把已经入队的 `pending` 基准运行标成失败。

#### Scenario: 成功提交基准任务

- **WHEN** 调用方对一个已有基准套件调用基准运行接口
- **THEN** 系统返回任务标识，对应运行记录为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 基准运行完成

- **WHEN** 基准任务成功执行完毕
- **THEN** 任务状态为 `completed`，且对应运行记录包含准确率与成本

#### Scenario: 取消尚未结束的基准任务

- **WHEN** 调用方取消一个仍处于 `pending` 或 `running` 的基准任务
- **THEN** 任务状态变为 `cancelled`，且不再把该运行标成 `completed`

#### Scenario: 重启保留已入队基准运行

- **WHEN** 基准运行已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 运行记录仍为 `pending`，且其任务标识仍然有效

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

### Requirement: 暂停的评估任务可以恢复

系统 SHALL 通过任务恢复接口接受调用方对自己名下、状态为 `paused` 的评估任务的恢复请求。恢复 SHALL 沿用原来的任务标识，把该任务状态置为 `pending`，并在发布队列消息之前完成落库。关联评估记录 SHALL 保持指向同一任务，且其状态变为 `pending`。非暂停任务、不属于调用方的任务，以及 `task_type` 不是评估的任务，SHALL 被拒绝，且不发布新的队列消息、不修改原任务记录。

#### Scenario: 恢复暂停的评估任务

- **WHEN** 调用方恢复一个属于自己、状态为 `paused` 的评估任务
- **THEN** 系统返回原来的任务标识，该任务状态为 `pending`，关联评估仍指向该任务且状态为 `pending`，队列消息在该状态落库之后发布

#### Scenario: 拒绝恢复非暂停任务

- **WHEN** 调用方恢复一个属于自己、状态不是 `paused` 的任务
- **THEN** 系统拒绝该请求，原任务记录保持不变，且不发布新的队列消息

#### Scenario: 拒绝恢复非评估任务

- **WHEN** 调用方恢复一个属于自己、状态为 `paused`、但类型不是评估的任务
- **THEN** 系统拒绝该请求，原任务记录保持不变，且不发布新的队列消息

#### Scenario: 拒绝恢复他人的任务

- **WHEN** 调用方恢复一个不属于自己的暂停任务
- **THEN** 系统拒绝该请求，且不发布新的队列消息
