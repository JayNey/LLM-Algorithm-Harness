## Purpose

定义评估任务被 worker 拾取后的真实执行语义：如何解析模型凭证与题目、逐 (策略 × 题目) 单元运行真实评估、记录每单元结果与累计成本、在预算触顶时暂停，以及模型/题目/单元失败与恢复时的状态回写。

## ADDED Requirements

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

系统 SHALL 支持对处于 `paused` 或 `failed` 的评估重新发起执行，从尚未完成的单元继续；已经写入结果的单元 SHALL NOT 被重复执行或产生重复结果记录，累计花费与计数 SHALL 在既有基础上继续而非从头重置。

#### Scenario: 暂停后恢复继续剩余单元

- **WHEN** 一个因预算触顶而 `paused` 的评估在提高预算后被重新发起执行
- **THEN** 仅剩余未完成的单元被执行，已完成单元的结果记录不重复，`completed_count` 从暂停时的值继续增长

### Requirement: 执行终态回写

系统 SHALL 在评估执行结束时把最终状态回写到评估记录：全部单元完成时置为 `completed`；被预算或用户暂停时置为 `paused`；执行过程发生不可恢复错误时置为 `failed` 并保存错误信息。既有的取消语义与「API 进程重启不把已入队 `pending` 评估标记为失败」的语义 SHALL 保持不变。

#### Scenario: 执行中抛出不可恢复错误

- **WHEN** 评估执行过程中发生未被单元级处理吸收的错误
- **THEN** 评估状态置为 `failed` 并保存错误信息，关联任务状态与之一致

#### Scenario: 全部完成置为 completed

- **WHEN** 评估的所有单元均成功执行且未触发预算暂停
- **THEN** 评估状态置为 `completed`，`completed_at` 被记录
