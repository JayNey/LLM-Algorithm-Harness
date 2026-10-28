# async-task-queue Specification

## Purpose
让实验、题目导入和基准测试进入与评估任务相同的异步队列，使调用方可以拿到任务标识并查询状态、进度和失败原因。

## Requirements

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

### Requirement: 题目导入可以作为异步任务执行

系统 SHALL 通过题目导入接口接受一次已登记导入作业的异步执行请求，立即返回任务标识和作业标识。入队 SHALL 在提交队列消息之前先把任务记录落库，且发布使用的队列任务标识与已落库记录一致。发布失败时 SHALL 把该任务标为 `failed` 并保存错误信息。导入完成或失败后，任务状态 SHALL 与导入作业的最终结果一致。执行期间系统 SHALL 在任务进度中报告已处理数量、总数量、由二者算出且落在 0 到 100 的完成百分比，以及当前条目序号。总数量为 0 时百分比 SHALL 为 0。当前步骤 SHALL 只包含条目序号，不得包含题目正文。调用方暂停一个正在执行的导入后，worker SHALL 在下一道题开始前停止，且不得把尚未完成的导入写入数据集。任务和导入作业都保持 `paused`。暂停后 SHALL 保留最后一次进度。

#### Scenario: 成功提交导入任务

- **WHEN** 调用方通过题目导入接口提交一个属于自己的已上传文件
- **THEN** 系统返回任务标识和作业标识，且不在 API 进程内执行导入

#### Scenario: 导入入队先落库后发布

- **WHEN** 题目导入接口提交异步执行
- **THEN** 任务记录在队列消息发布之前已落库，且发布使用的队列任务标识与该记录一致

#### Scenario: 导入入队发布失败

- **WHEN** 题目导入接口在任务记录落库后无法发布队列消息
- **THEN** 该任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 查询导入进度

- **WHEN** 导入任务正在执行且已知总数量
- **THEN** 任务进度返回已处理数量、总数量、由二者算出且落在 0 到 100 的完成比例，以及当前条目序号，且不包含题目正文

#### Scenario: 暂停正在执行的导入

- **WHEN** 导入正在执行，调用方将该任务暂停，且仍有尚未处理的题目
- **THEN** worker 不再处理这些题目，不把这部分导入写入数据集，任务和导入作业都为 `paused`

#### Scenario: 导入对象不存在

- **WHEN** 调用方提交的导入作业不存在或不属于该调用方
- **THEN** 系统拒绝执行，且不把其他用户的导入数据写入数据集

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

### Requirement: 通用任务创建先落库后发布

系统 SHALL 通过通用任务创建接口为调用方创建异步任务。公开接口 SHALL 仅允许 evaluation、experiment、import 和 benchmark 业务类型与其对应的现有 Celery 任务名精确配对。内部维护任务、未知任务和类型与名称不匹配的请求 SHALL 返回 403，且不得创建任务记录或发布队列消息。任务记录 SHALL 在队列消息发布之前落库，且发布使用的队列任务标识与已落库记录一致。发布失败时 SHALL 把该任务标为 `failed` 并保存错误信息。

#### Scenario: 通用任务创建先落库

- **WHEN** 调用方通过通用任务创建接口提交合法业务任务
- **THEN** 任务记录在队列消息发布之前已落库，且发布使用的队列任务标识与该记录一致

#### Scenario: 通用任务发布失败

- **WHEN** 通用任务创建接口在任务记录落库后无法发布队列消息
- **THEN** 该任务状态为 `failed`，且错误信息可从任务记录读出

#### Scenario: 拒绝公开提交内部清理任务

- **WHEN** 已登录调用方指定内部清理 Celery 任务，即使把任务类型伪装成合法业务类型
- **THEN** 接口返回 403，不创建任务、不发布消息，且其他用户任务记录保持不变

#### Scenario: 拒绝未知任务或类型名称不匹配

- **WHEN** 调用方指定未知 Celery 任务、未知任务类型或不匹配的业务类型与任务名
- **THEN** 接口返回 403，且不创建任务记录或发布队列消息

### Requirement: 真实 worker 执行日志
系统 SHALL 持久化真实异步任务的生命周期和已报告的数值进度，并记录评估单元开始和结束事件；日志 SHALL 关联服务端持久化的任务所有者，入库前脱敏，排除原始异常、题目正文、生成代码和请求参数。日志采集故障 SHALL 不改变任务结果，且日志可在 API 重启后读取。

#### Scenario: 四类 worker 生命周期与进度
- **WHEN** 评估、实验、导入或基准 worker 实际执行并报告状态或进度
- **THEN** 日志中出现相应事件，评估包含单元开始和成功或失败事件，完成或失败等级与事件相符

#### Scenario: 脱敏和故障隔离
- **WHEN** 事件字段包含凭据或日志存储不可用
- **THEN** 持久化日志中不出现凭据，存储失败不改变业务状态或替换业务异常，降级诊断不包含原始错误

### Requirement: 执行日志权限与检索
系统 SHALL 在查询和下载前从实际业务数据库校验 AsyncTask 所有者，支持任务 ID 与有效关联评估 ID，兼容旧 run。跨用户、缺失或失效关联 SHALL 返回 404；未登录 SHALL 返回 401；全局日志 SHALL 仅供服务端授权管理员访问。查询 SHALL 支持级别、时间、文本与分页，下载 SHALL 使用相同权限和过滤条件、忽略分页并保留导出上限及计数头。

#### Scenario: 任务与评估别名及越权
- **WHEN** 用户使用自己的异步任务 ID 或关联评估 ID 查询和下载
- **THEN** 返回同一份保留日志；其他用户不能读取，失效关联不能通过旧映射绕过校验

#### Scenario: 查询和下载一致
- **WHEN** 用户按级别、时间或文本过滤并下载执行日志
- **THEN** 查询和 JSONL 下载的记录集合一致，分页不截断导出，非法过滤条件被拒绝

#### Scenario: 旧日志与重启兼容
- **WHEN** API 重启或用户查询旧 run 的日志
- **THEN** 保留的事件仍可读取且不与同名异步任务日志混淆

### Requirement: 实际任务耗时与成功率统计
系统 SHALL 记录真实业务任务首次开始与终态结束时间，状态及进度更新均支持记录，重复通知不得覆盖已有时间；任务重新 running SHALL 清除旧结束时间。管理员性能接口 SHALL 基于持久化业务 AsyncTask 返回全部任务与评估任务统计，明确累计范围、样本数与秒单位。耗时 SHALL 仅使用 completed/failed 且开始结束有效的记录；成功率 SHALL 为实际开始的 completed/(completed+failed)，取消、未执行任务不计入。耗时包含暂停和重试间隔，排除首次排队时间。

#### Scenario: 时间记录与重试
- **WHEN** 任务通过状态或进度进入 running 后结束，或结束后重新进入 running
- **THEN** 首次开始与终态结束被记录，重复通知保留时间，重新 running 清空旧结束时间

#### Scenario: 真实任务聚合
- **WHEN** 存在已执行的成功、失败任务及取消、未执行或时间无效的任务
- **THEN** 性能接口按上述口径返回平均执行秒数、成功率和样本数，评估子集不包含其他类型

#### Scenario: 空样本与不可用
- **WHEN** 没有有效样本或任务数据库不可用
- **THEN** 无样本指标返回 null，数据库不可用返回 unavailable 且不暴露异常内容

### Requirement: 队列积压按来源独立展示

管理员监控 SHALL 只读采集配置的 Redis broker 中各业务队列等待执行的消息数量，覆盖所有配置的优先级分桶及键前缀，并返回每队列数量及总数。系统状态 SHALL 分别展示 broker_queue、database_pending 和 worker_reserved；数据库 pending 来自持久化 AsyncTask，worker reserved 只来自回复的 worker，三者不相加也不互相推算。探测 SHALL 遵循现有启用开关、总超时和缓存；失败、未启用、配置非法或不支持 transport 时等待数 SHALL 为 null，真实空队列 SHALL 为 0。采集 SHALL NOT 消费消息、读取任务内容、修改业务状态或暴露凭据。

#### Scenario: 多队列优先级积压
- **WHEN** 已配置的两个 Redis 队列在不同优先级分桶分别有 3 和 2 条消息
- **THEN** 返回各队列 3 和 2，总数 5，不计入未配置的队列和 unacked

#### Scenario: 独立展示三类计数
- **WHEN** broker 等待数为 5，数据库 pending 为 7，回复 worker reserved 为 2
- **THEN** system/status 分别返回 5、7、2，不将其中任一值作为其他指标或总积压

#### Scenario: 探测故障或关闭
- **WHEN** broker 超时、不可用、配置非法、不支持 transport 或未启用探测
- **THEN** broker 等待数为 null，且不泄露连接信息，数据库与 worker 的独立计数语义保持不变

#### Scenario: 空队列
- **WHEN** Redis 正常且所有配置队列均为空
- **THEN** 每队列及总等待数为 0，探测不创建或消费任务消息

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
