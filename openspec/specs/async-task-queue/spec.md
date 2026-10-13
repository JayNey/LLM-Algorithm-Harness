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
