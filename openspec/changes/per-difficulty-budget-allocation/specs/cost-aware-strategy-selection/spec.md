# cost-aware-strategy-selection Specification

## Purpose

在评估流程中提供成本敏感的策略执行方式：按题目难度映射策略，并在运行中监控已知定价成本，达到预算上限后自动降级到最便宜策略。本次变更将预算控制从单一全局上限扩展为支持每难度独立预算与隔离降级。

## MODIFIED Requirements

### Requirement: 运行中预算降级

系统 SHALL 支持通过 `--budget-cap USD` 设置本次任务的累计成本上限：逐题累计已知定价的调用成本，达到上限后，后续题目 SHALL 自动改用映射中最便宜策略执行，其结果 SHALL 标记 `cost_downgraded=true`；监控覆盖同一任务的完整成本，`--resume` 恢复时 SHALL 先回放已完成题目的成本再继续执行，不追溯其他运行的历史。

#### Scenario: 达上限后降级

- **WHEN** 运行中累计已知成本达到预算上限，后续仍有未执行题目
- **THEN** 后续题目全部以映射中最便宜策略执行，结果带 `cost_downgraded=true`，且已完成的题目结果不受影响

#### Scenario: 未达上限不降级

- **WHEN** 运行全程累计成本未达上限
- **THEN** 所有题目按映射策略执行，无结果被标记 `cost_downgraded`

## ADDED Requirements

### Requirement: 按难度的预算分配

系统 SHALL 支持通过 `--budget-allocation DIFF=USD`（或配置等价字段）为各难度设置独立预算：每个难度独立累计已知定价成本，某难度达到其预算后，SHALL 仅该难度的剩余题目降级到映射中最便宜策略，其他难度的题目执行方式不受影响；分配与全局上限可同时使用，任一触顶即对该题生效；`--resume` 回放 SHALL 按题目所属难度结算进各难度预算。

#### Scenario: 单难度触顶隔离降级

- **WHEN** easy 难度预算耗尽而 medium/hard 预算未动用，后续仍有各难度未执行题目
- **THEN** 仅 easy 的剩余题目被降级并标记 `cost_downgraded=true`，medium/hard 题目继续按映射策略执行

#### Scenario: 分配与全局上限并存

- **WHEN** 同时设置 `--budget-cap` 与 `--budget-allocation`
- **THEN** 全局累计触顶影响所有难度的剩余题目，单难度触顶仅影响该难度，先触发者生效

#### Scenario: resume 按难度回放

- **WHEN** 带分配预算的任务中断后 `--resume` 恢复
- **THEN** 已完成题目的成本按其难度回放进对应难度预算，各难度后续降级判定基于回放后的余量

### Requirement: 预算分配配置与校验

预算分配 SHALL 通过 `--budget-allocation DIFF=USD`（或配置字段 `budget_allocation`）提供：难度键限定 easy/medium/hard，金额必须为正数；与 `--budget-cap` 一样 SHALL 依赖难度映射存在，且与 `--strategy` 互斥；校验失败 SHALL 报错退出且不发起任何模型调用。未出现在分配中的难度 SHALL 无独立预算上限（仅受全局上限约束）。

#### Scenario: 配置校验

- **WHEN** 提供非法难度键、非正金额、或在无难度映射时提供分配
- **THEN** 启动报错并以非零码退出，不执行任何评估

#### Scenario: 未分配难度无上限

- **WHEN** 分配只提供 easy 与 medium，数据集包含 hard 题目且全局上限未设
- **THEN** hard 题目全程按映射策略执行，不触发降级

### Requirement: 按难度成本呈现

报告 SHALL 在按难度统计的每个难度桶中呈现该难度的累计已知定价成本 `cost_usd`（增量字段，既有统计不变）；运行结束的成本控制摘要 SHALL 逐难度列出预算使用情况（累计成本 / 预算上限 / 降级题数），未分配的难度不列出；usage 未知的结果不计入任何难度累计值、按其难度计入未知计数。

#### Scenario: 成本分布呈现

- **WHEN** 带分配预算的运行完成
- **THEN** 报告按难度桶给出 cost_usd，摘要逐难度给出累计成本、预算与降级数，数值与手算一致
