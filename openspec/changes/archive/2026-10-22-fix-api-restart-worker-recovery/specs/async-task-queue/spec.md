## MODIFIED Requirements

### Requirement: 实验可以作为异步任务执行

系统 SHALL 通过实验运行接口接受一次处于 `pending` 的已有实验的异步执行请求，立即返回任务标识，且实验记录保持 `pending`，直到 worker 开始执行。入队 SHALL 在提交队列消息之前先把任务记录落库，且发布使用的队列任务标识与已落库记录一致。发布失败时 SHALL 把该任务标为 `failed` 并保存错误信息。执行期间状态 SHALL 保持在 `pending`、`running`、`paused`、`completed`、`failed` 或 `cancelled` 之一。执行期间系统 SHALL 在任务进度中报告完成百分比和当前步骤。百分比 SHALL 由已完成组合数与组合总数算出，并落在 0 到 100；组合总数为 0 时百分比 SHALL 为 0。当前步骤 SHALL 标识当前组合的模型、策略和重复序号，且不得包含题目正文。任务完成后，实验记录 SHALL 反映最终状态；失败时 SHALL 保存错误信息。调用方暂停一个正在执行的实验后，worker SHALL 在下一个组合开始前停止继续派发，任务和实验记录都保持 `paused`，且不得再被写成 `completed` 或 `failed`。已经开始的组合可以做完。暂停后 SHALL 保留最后一次进度。API 进程重启 SHALL NOT 把关联活跃 AsyncTask（`pending`、`running` 或 `paused`）的 `pending` 或 `running` 实验标成失败。

#### Scenario: 成功提交实验任务

- **WHEN** 调用方对一个处于 `pending` 的已有实验调用实验运行接口
- **THEN** 系统返回任务标识，实验记录仍为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 实验入队先落库后发布

- **WHEN** 实验运行接口提交异步执行
- **THEN** 任务记录在队列消息发布之前已落库，且发布使用的队列任务标识与该记录一致

#### Scenario: 实验入队发布失败

- **WHEN** 实验运行接口在任务记录落库后无法发布队列消息
- **THEN** 该任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 查询实验进度

- **WHEN** 实验正在执行，且已知组合总数
- **THEN** 任务进度包含落在 0 到 100 的百分比，以及当前组合的模型、策略和重复序号，且不包含题目正文

#### Scenario: 暂停正在执行的实验

- **WHEN** 实验正在执行，调用方将该任务暂停，且仍有尚未开始的组合
- **THEN** worker 不再开始这些组合，任务和实验记录都为 `paused`，且不会变成 `completed` 或 `failed`

#### Scenario: 实验执行失败时留下错误

- **WHEN** 实验执行过程中发生业务错误或运行失败，且该任务没有被暂停
- **THEN** 任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 重启保留已入队实验

- **WHEN** 实验已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 实验记录仍为 `pending`，且其任务标识仍然有效

#### Scenario: 重启保留 worker 正在执行的实验

- **WHEN** 实验已为 `running`，关联活跃 AsyncTask，独立 worker 仍在执行，此时 API 进程重启
- **THEN** 实验与任务仍为 `running`；worker 随后正常完成，实验关联产物目录与完成时间，且结果可查询。

### Requirement: 基准测试可以作为异步任务执行

系统 SHALL 通过基准运行接口创建一次基准运行并接受其异步执行请求，立即返回任务标识，且运行记录保持 `pending`，直到 worker 开始执行。入队 SHALL 在提交队列消息之前先把任务记录落库，且发布使用的队列任务标识与已落库记录一致。发布失败时 SHALL 把该任务标为 `failed` 并保存错误信息。执行期间系统 SHALL 在任务进度中报告完成百分比和当前步骤。百分比 SHALL 由已完成题目数与题目总数算出，并落在 0 到 100；题目总数为 0 时百分比 SHALL 为 0。当前步骤 SHALL 标识当前题目的策略和题目标识，且不得包含题目正文。结束后系统 SHALL 把准确率、成本与结果摘要写入该运行记录。失败时 SHALL 把运行标记为 `failed` 并保存错误信息。调用方暂停一个正在执行的基准后，worker SHALL 在下一道题开始前停止继续派发，任务和运行记录都保持 `paused`，且不得再被写成 `completed` 或 `failed`。已经开始的题目可以做完。暂停后 SHALL 保留最后一次进度。API 进程重启 SHALL NOT 把关联活跃 AsyncTask（`pending`、`running` 或 `paused`）的 `pending` 或 `running` 基准运行标成失败。

#### Scenario: 成功提交基准任务

- **WHEN** 调用方对一个已有基准套件调用基准运行接口
- **THEN** 系统返回任务标识，对应运行记录为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 基准入队先落库后发布

- **WHEN** 基准运行接口提交异步执行
- **THEN** 任务记录在队列消息发布之前已落库，且发布使用的队列任务标识与该记录一致

#### Scenario: 基准入队发布失败

- **WHEN** 基准运行接口在任务记录落库后无法发布队列消息
- **THEN** 该任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 查询基准进度

- **WHEN** 基准正在执行，且已知题目总数
- **THEN** 任务进度包含落在 0 到 100 的百分比，以及当前题目的策略和题目标识，且不包含题目正文

#### Scenario: 基准运行完成

- **WHEN** 基准任务成功执行完毕，且执行期间没有被暂停
- **THEN** 任务状态为 `completed`，且对应运行记录包含准确率与成本

#### Scenario: 暂停正在执行的基准

- **WHEN** 基准正在执行，调用方将该任务暂停，且仍有尚未开始的题目
- **THEN** worker 不再开始这些题目，任务和运行记录都为 `paused`，且不会变成 `completed` 或 `failed`

#### Scenario: 取消尚未结束的基准任务

- **WHEN** 调用方取消一个仍处于 `pending` 或 `running` 的基准任务
- **THEN** 任务状态变为 `cancelled`，且不再把该运行标成 `completed`

#### Scenario: 重启保留已入队基准运行

- **WHEN** 基准运行已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 运行记录仍为 `pending`，且其任务标识仍然有效

#### Scenario: 重启保留 worker 正在执行的基准

- **WHEN** 基准已为 `running`，关联活跃 AsyncTask，独立 worker 仍在执行，此时 API 进程重启
- **THEN** 运行与任务仍为 `running`；worker 随后可以正常保存完成状态、准确率、成本与结果。

### Requirement: 评估可以作为异步任务执行

系统 SHALL 通过评估启动接口接受一次处于 `pending` 的已有评估的异步执行请求，立即返回任务标识，且评估记录保持 `pending`，直到 worker 开始执行。入队 SHALL 在提交 Celery 消息之前先把任务记录与其到评估的关联落库，使 worker 能可靠解析到关联任务。执行期间状态 SHALL 保持在 `pending`、`running`、`paused`、`completed`、`failed` 或 `cancelled` 之一。执行期间系统 SHALL 在任务进度中报告完成百分比和当前步骤。百分比 SHALL 由已完成单元数与单元总数算出，并落在 0 到 100；单元总数为 0 时百分比 SHALL 为 0。当前步骤 SHALL 标识即将执行单元的策略和题目标识，且不得包含题目正文。任务完成后评估记录 SHALL 反映最终状态；失败时 SHALL 保存错误信息。取消一个已入队评估 SHALL revoke 对应 Celery 任务并把状态置为 `cancelled`。取消一个正在执行且仍有尚未开始单元的评估时，系统 SHALL 同时请求协作式取消：worker SHALL 在下一个尚未开始的单元之前停止派发，已经开始的单元可以做完，评估与任务 SHALL 保持 `cancelled`，后续收尾不得把它们写成 `completed`。调用方暂停一个正在执行的评估后，任务 SHALL 保持 `paused`，且暂停后 SHALL 保留最后一次进度。API 进程重启 SHALL NOT 把关联活跃 AsyncTask（`pending`、`running` 或 `paused`）的 `pending` 或 `running` 评估标成失败。

#### Scenario: 成功提交评估任务

- **WHEN** 调用方对一个处于 `pending` 的已有评估调用评估启动接口
- **THEN** 系统返回任务标识，评估记录仍为 `pending`，且该任务可被查询为 `pending` 或 `running`

#### Scenario: 入队先落库后发布

- **WHEN** 评估启动接口提交异步执行
- **THEN** 任务记录与其到评估的关联在 Celery 消息发布之前已落库，worker 能解析到该关联任务

#### Scenario: 查询评估进度

- **WHEN** 评估正在执行，且已知单元总数
- **THEN** 任务进度包含落在 0 到 100 的百分比，以及即将执行单元的策略和题目标识，且不包含题目正文

#### Scenario: 暂停后保留评估进度

- **WHEN** 评估正在执行且已写入进度，调用方将该任务暂停
- **THEN** 任务保持 `paused`，且最后一次进度仍可查询

#### Scenario: 取消已入队评估

- **WHEN** 调用方取消一个仍处于 `pending` 或 `running` 的评估
- **THEN** 系统 revoke 对应 Celery 任务，评估与任务状态变为 `cancelled`

#### Scenario: 取消正在执行的评估

- **WHEN** 评估正在执行且仍有尚未开始的单元，调用方取消该任务
- **THEN** worker 不再派发这些单元，评估与任务保持 `cancelled`，且后续收尾不会把它们写成 `completed`

#### Scenario: 重启保留已入队评估

- **WHEN** 评估已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 评估记录仍为 `pending`，且其任务标识仍然有效

#### Scenario: 重启保留 worker 正在执行的评估

- **WHEN** 评估已为 `running`，关联活跃 AsyncTask，独立 worker 仍在执行，此时 API 进程重启
- **THEN** 评估与任务仍为 `running`，不附加重启失败原因；worker 可以继续正常完成。
