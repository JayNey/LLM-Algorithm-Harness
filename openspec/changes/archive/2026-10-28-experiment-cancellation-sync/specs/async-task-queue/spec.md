## MODIFIED Requirements

### Requirement: 实验可以作为异步任务执行

系统 SHALL 通过实验运行接口接受一次处于 `pending` 的已有实验的异步执行请求，立即返回任务标识，且实验记录保持 `pending`，直到 worker 开始执行。入队 SHALL 在提交队列消息之前先把任务记录落库，且发布使用的队列任务标识与已落库记录一致。发布失败时 SHALL 把该任务标为 `failed` 并保存错误信息。执行期间状态 SHALL 保持在 `pending`、`running`、`paused`、`completed`、`failed` 或 `cancelled` 之一。执行期间系统 SHALL 在任务进度中报告完成百分比和当前步骤。百分比 SHALL 由已完成组合数与组合总数算出，并落在 0 到 100；组合总数为 0 时百分比 SHALL 为 0。当前步骤 SHALL 标识当前组合的模型、策略和重复序号，且不得包含题目正文。任务完成后，实验记录 SHALL 反映最终状态；失败时 SHALL 保存错误信息。调用方暂停一个正在执行的实验后，worker SHALL 在下一个组合开始前停止继续派发，任务和实验记录都保持 `paused`，且不得再被写成 `completed` 或 `failed`。已经开始的组合可以做完。暂停后 SHALL 保留最后一次进度。取消实验 SHALL 原子同步任务与实验的 cancelled 状态和结束时间，保持所有者隔离；晚到状态写入 SHALL NOT 覆盖 cancelled，已完成或失败的实验 SHALL 拒绝取消。取消后 worker SHALL 在下一组合前停止派发。API 进程重启 SHALL NOT 把关联活跃 AsyncTask（`pending`、`running` 或 `paused`）的 `pending` 或 `running` 实验标成失败。

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

- **WHEN** 实验执行过程中发生业务错误或运行失败，且该任务没有被暂停或取消
- **THEN** 任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 重启保留已入队实验

- **WHEN** 实验已提交异步执行且仍为 `pending`，随后 API 进程重启
- **THEN** 实验记录仍为 `pending`，且其任务标识仍然有效

#### Scenario: 重启保留 worker 正在执行的实验

- **WHEN** 实验已为 `running`，关联活跃 AsyncTask，独立 worker 仍在执行，此时 API 进程重启
- **THEN** 实验与任务仍为 `running`；worker 随后正常完成，实验关联产物目录与完成时间，且结果可查询。

#### Scenario: 取消实验后刷新与删除

- **WHEN** 所有者取消 pending、running 或 paused 的实验任务
- **THEN** 任务和实验在同一事务中成为 cancelled，保留首次开始时间并同步取消完成时间；重新查询仍为 cancelled，按现有删除规则可以删除实验。

#### Scenario: 取消先于晚到写入

- **WHEN** 取消已提交，随后 Worker 启动、进度、成功、异常或 Celery 状态回填到达
- **THEN** 两层均保持 cancelled，取消时间与最后进度不变，不再启动后续组合；实验已删除时也不重建记录或把任务改成 failed。

#### Scenario: 完成先于取消

- **WHEN** Worker 已提交 completed 或 failed，随后取消请求到达（包括使用较早读取的 running 对象）
- **THEN** 拒绝取消，保留任务与实验终态、结果和结束时间。

#### Scenario: 取消所有权隔离

- **WHEN** 调用方取消他人的任务，或自己的任务引用他人的实验
- **THEN** 他人的任务与实验状态均不被修改；跨用户任务请求被拒绝。
