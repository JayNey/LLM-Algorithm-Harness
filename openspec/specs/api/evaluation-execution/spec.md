# api/evaluation-execution Specification

## Purpose
定义评估任务被 worker 拾取后的真实执行语义：如何解析模型凭证与题目、逐 (策略 × 题目) 单元运行真实评估、记录每单元结果与累计成本、在预算触顶时暂停，以及模型/题目/单元失败与恢复时的状态回写。

## Requirements

### Requirement: 评估单元真实执行

系统 SHALL 对评估的每个 (策略 × 题目) 组合执行真实评估——调用评估所配置的 LLM 并在沙箱中运行产生的代码——而非返回占位或模拟结果。执行 SHALL NOT 产生任何标记为 mock 的成功结果。

#### Scenario: 全部单元真实执行成功

- **WHEN** 一个包含 2 个策略与 2 个题目的评估被 worker 执行，且所有单元的 LLM 调用与沙箱运行均成功
- **THEN** 4 个单元全部真实执行完成，评估状态置为 `completed`，`completed_count` 等于 4，且没有任何单元结果被标记为 mock

#### Scenario: 单元产出真实度量

- **WHEN** 一个单元真实执行结束
- **THEN** 该单元结果记录包含来自真实执行的度量（如通过状态、token 或成本相关指标），而非固定的占位值

### Requirement: 模型与凭证解析

系统 SHALL 使用评估记录持久化的 `model` 与 `api_key_id` 解析出真实 LLM 凭证。当凭证无法解析（密钥不存在、不属于该评估所有者、或存储的凭证不可用）时，评估 SHALL 标记为 `failed` 并保存明确的错误信息，且 SHALL NOT 产生任何单元结果。

#### Scenario: 凭证不可解析时评估失败

- **WHEN** 评估的 `api_key_id` 无法解析出可用凭证
- **THEN** 评估状态置为 `failed`，`error_message` 说明凭证不可用，且没有写入任何 `evaluation_results` 行

#### Scenario: 缺少模型标识时评估失败

- **WHEN** 评估记录没有可用于执行的 `model`
- **THEN** 评估状态置为 `failed` 并保存说明缺少模型的错误信息，不发起任何 LLM 调用

### Requirement: 题目解析与缺失处理

系统 SHALL 按评估的 `problem_ids` 从题库解析出对应题目。当某个题目在题库中缺失时，其对应的每个单元 SHALL 记为失败并写明缺失原因；其余可解析的题目 SHALL 继续正常执行，整个评估 SHALL NOT 因个别题目缺失而整体中止。

#### Scenario: 部分题目缺失其余继续

- **WHEN** 评估的 `problem_ids` 中有一个题目在题库中不存在，其余题目存在
- **THEN** 缺失题目对应的单元结果记为失败并附缺失原因，存在题目的单元正常执行，评估聚合的 `failed_count` 计入缺失单元

### Requirement: 逐单元结果落库与聚合

系统 SHALL 在每个单元执行结束后写入一条对应的结果记录，包含该单元的状态与度量，失败时包含错误信息。评估记录 SHALL 聚合已完成单元数与失败单元数，使进度可在不查询单条结果的情况下反映整体执行情况。

#### Scenario: 每单元写入一条结果

- **WHEN** 一个评估的所有单元执行完毕
- **THEN** 每个 (策略 × 题目) 单元都有一条结果记录，其状态与该单元真实执行结果一致

#### Scenario: 聚合计数的口径

- **WHEN** 评估执行结束，其中部分单元成功、部分失败
- **THEN** `completed_count` 与 `failed_count` 之和等于单元总数，且与实际成功/失败单元数一致

### Requirement: 成本累计与预算暂停

系统 SHALL 把每个单元真实执行产生的花费累计到评估的 `spent_usd`。当评估设置了 `budget_cap_usd` 且累计花费达到该上限时，系统 SHALL 停止调度后续尚未开始的单元，把评估状态置为 `paused`，并保留已完成单元的结果与已累计花费。未设置预算上限时，评估 SHALL 执行完全部单元。

#### Scenario: 达到预算上限时暂停

- **WHEN** 评估设置了 `budget_cap_usd`，执行过程中累计 `spent_usd` 达到该上限且仍有单元未开始
- **THEN** 未开始的单元不再执行，评估状态置为 `paused`，已完成单元的结果与 `spent_usd` 保留

#### Scenario: 无预算上限时跑完全部单元

- **WHEN** 评估未设置 `budget_cap_usd`
- **THEN** 所有单元均被执行，评估按最终执行结果进入 `completed` 或 `failed`，`spent_usd` 反映全部单元的真实花费

#### Scenario: 单元花费无可用定价时诚实计入

- **WHEN** 某单元真实执行完成，但其 LLM 调用没有可用的定价元数据（无法换算为确切 USD 花费）
- **THEN** 系统 SHALL NOT 伪造该单元的花费，`spent_usd` 只累计已知定价的真实花费，该单元结果度量 SHALL 标记花费为未知；因此即使设置了 `budget_cap_usd`，未定价的单元也不推动 `spent_usd` 触发暂停

### Requirement: 恢复继续不重复已完成单元

系统 SHALL 支持对处于 `paused` 或 `failed` 的评估重新发起执行，从尚未完成的单元继续；worker 丢失后重投递的评估若遗留 `running` 检查点，SHALL 同样从检查点恢复并重新排队中断的单元。已经写入结果的单元 SHALL NOT 被重复执行或产生重复结果记录，累计花费与计数 SHALL 在既有基础上继续而非从头重置。恢复 SHALL 校验既有配置和数据指纹。

#### Scenario: 暂停后恢复继续剩余单元

- **WHEN** 一个因预算触顶而 `paused` 的评估在提高预算后被重新发起执行
- **THEN** 仅剩余未完成的单元被执行，已完成单元的结果记录不重复，`completed_count` 从暂停时的值继续增长

#### Scenario: worker 丢失后从 running 检查点恢复

- **WHEN** worker 丢失后任务被重投递，检查点为 `running` 且包含已完成、执行中和排队单元
- **THEN** 系统保留已完成单元，只重跑中断与排队单元，结果不重复、费用继续累计，任务与评估反映最终状态

#### Scenario: running 检查点指纹不匹配

- **WHEN** 重投递评估的既有 `running` 检查点与当前配置或数据指纹不一致
- **THEN** 系统拒绝恢复，不执行新单元、不覆盖检查点

### Requirement: 执行终态回写

系统 SHALL 在评估执行结束时把最终状态回写到评估记录：全部单元完成时置为 `completed`；被预算或用户暂停时置为 `paused`；执行过程发生不可恢复错误时置为 `failed` 并保存错误信息。既有的取消语义与「API 进程重启不把已入队 `pending` 评估标记为失败」的语义 SHALL 保持不变。

#### Scenario: 执行中抛出不可恢复错误

- **WHEN** 评估执行过程中发生未被单元级处理吸收的错误
- **THEN** 评估状态置为 `failed` 并保存错误信息，关联任务状态与之一致

#### Scenario: 全部完成置为 completed

- **WHEN** 评估的所有单元均成功执行且未触发预算暂停
- **THEN** 评估状态置为 `completed`，`completed_at` 被记录

### Requirement: 创建入口拒绝重复输入

系统 SHALL 在创建评估请求的入口拒绝含重复项的 `strategy_names` 或 `problem_ids`，返回 HTTP 400（`validation_error`）且错误详情 SHALL 以对应字段名定位，SHALL NOT 创建任何评估记录或待执行单元。无重复的合法请求行为 SHALL 保持不变。

#### Scenario: 重复的策略名被入口拒绝

- **WHEN** 创建评估请求的 `strategy_names` 含重复值（如 `["vanilla", "vanilla"]`）而 `problem_ids` 无重复
- **THEN** 响应为 HTTP 400、`error` 为 `validation_error`，`details` 以 `strategy_names` 为键给出原因，且库中没有任何新建的评估记录

#### Scenario: 重复的题目 ID 被入口拒绝

- **WHEN** 创建评估请求的 `problem_ids` 含重复值（如 `["p1", "p1"]`）
- **THEN** 响应为 HTTP 400，`details` 以 `problem_ids` 为键给出原因，不创建评估记录也不产生任何单元

#### Scenario: 无重复的合法请求不受影响

- **WHEN** `strategy_names` 与 `problem_ids` 均不含重复项
- **THEN** 评估按既有语义创建成功（201），单元数等于策略数 × 题目数

### Requirement: 进度百分比以单元总数为分母

系统 SHALL 以单元总数（题目数 × 策略数）作为进度 `percentage` 的分母，其值 SHALL 恒落在 [0, 100] 区间内。在进度接口与聚合回退口径下，`progress.total` SHALL 保持题目数口径不变，因此 `current`/`total` 的比值与 `percentage` 的分母不同（若存在 worker 实时上报的 `async_task.progress`，其 `current`/`total` 均为单元数口径，不受本约束）。

#### Scenario: 多策略全部完成时百分比不溢出

- **WHEN** 一个 2 策略 × 2 题目的评估完成了全部 4 个单元（`completed_count=4`、`problem_count=2`）
- **THEN** `percentage` 等于 100 而非 200，列表与详情端点均正常返回 200，不因超出上界而校验失败

#### Scenario: 部分完成时按单元占比

- **WHEN** 上述评估已完成 2 个单元（共 4 个），通过进度接口查询
- **THEN** `percentage` 为 50（以单元总数 4 为分母），而同一响应里的 `total` 仍为题目数 2、`current` 为已完成单元数 2——两个分母不同，因此 `current/total` 的比值不等于 `percentage`

### Requirement: 用户评估并发准入

系统 SHALL 在评估提交时以用户为作用域，原子限制该用户已入队或运行中的评估任务总数。配置 `MAX_CONCURRENT_EVALUATIONS_PER_USER` SHALL 是正整数，默认 5。该限额 SHALL 在共享同一业务库的不同提交进程及 worker 间生效；超限 SHALL 不发布任务消息，不留下新增活动任务，HTTP 启动入口 SHALL 返回 429。草稿、暂停和终态任务 SHALL 不占用额度；恢复 SHALL 重新受限。不同用户额度 SHALL 独立。

#### Scenario: 跨进程同时提交
- **WHEN** 同一用户仅剩一个名额，多个进程同时提交不同评估
- **THEN** 最多一个提交成功，其余超限拒绝，数据库活动任务数不突破上限

#### Scenario: 不同用户独立
- **WHEN** 用户甲用尽额度，用户乙尚有空闲额度
- **THEN** 甲的新启动被拒绝，乙仍可提交

#### Scenario: 状态和恢复
- **WHEN** 用户存在草稿、暂停、完成、失败或取消任务，并恢复其中可恢复的评估
- **THEN** 这些旧状态不占用额度，恢复的新任务须重新检查额度；超限恢复不发布消息

#### Scenario: 所有提交入口与失败回滚
- **WHEN** 评估经启动、异步创建或恢复入口提交，或提交中发布消息失败
- **THEN** 各入口均执行同一限额检查，拒绝或发布失败不会新增占用额度

### Requirement: 用户评估并发额度查询
系统 SHALL 在现有 GET /api/v1/quotas 和 GET /api/v1/quotas/usage 中向已认证用户返回 evaluation_concurrency.limit、used、remaining。limit SHALL 使用准入配置 MAX_CONCURRENT_EVALUATIONS_PER_USER；used SHALL 仅计当前用户持久化 AsyncTask 中 task_type=evaluation 且状态为 pending/running 的任务；remaining SHALL 等于 max(limit-used,0)。查询 SHALL 只读且不轮询 Celery，不通过请求参数选择其他用户，不把数据库失败伪装成零用量。

#### Scenario: 空闲与自定义限额
- **WHEN** 用户无活动评估且配置限额为 3
- **THEN** 两个配额别名均返回 limit=3、used=0、remaining=3

#### Scenario: 状态与所有者隔离
- **WHEN** 存在本人 pending/running 评估及其他用户任务、其他类型任务、草稿、paused/completed/failed/cancelled 任务
- **THEN** 仅本人 pending/running 评估占用额度，身份参数不能更改查询所有者

#### Scenario: 状态变化与超限历史
- **WHEN** 任务进入暂停或终态后重新查询，或已有活动任务数超过当前配置
- **THEN** 查询反映已提交状态；超限时 used 保留真实值且 remaining=0

#### Scenario: 未认证及只读查询
- **WHEN** 未认证调用配额别名，或已认证用户查询
- **THEN** 未认证返回 401；已认证查询不修改任务、不调用 Celery，响应禁用缓存
