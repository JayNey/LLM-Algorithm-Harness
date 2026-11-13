# cost-aware-strategy-selection Specification

## Purpose
在评估流程中提供成本敏感的策略执行方式：按题目难度映射策略，并在运行中监控已知定价成本，达到预算上限后自动降级到最便宜策略。功能默认关闭；映射基于数据集难度标注，降级为确定性阶梯规则，不保证全局最优。

## Requirements

### Requirement: 按难度映射策略选择

系统 SHALL 支持通过 `--difficulty-strategy DIFF=STRATEGY`（或配置文件等价字段）为 easy/medium/hard 难度分别指定策略；选择器模式下每个题目按自身难度路由到映射策略，一题只执行一次，结果 SHALL 记录实际使用的策略名。

#### Scenario: 题目按难度路由

- **WHEN** 以 `easy=vanilla medium=chain_of_thought hard=multi_round_feedback` 启用选择器并运行含三种难度的数据集
- **THEN** 每个题目恰好执行一次，且使用的策略与其难度映射一致

#### Scenario: 合并报告

- **WHEN** 选择器模式运行完成
- **THEN** 产出单一合并报告（报告名 `cost_aware`），按难度维度的统计保留，且每条结果可区分实际策略

### Requirement: 映射与互斥校验

系统 SHALL 在启动时校验：数据集中出现的难度全部被映射覆盖，映射的策略名合法且存在于配置的策略列表中；选择器与 `--strategy` 互斥；校验失败 SHALL 报错退出且不发起任何模型调用。

#### Scenario: 未覆盖难度报错

- **WHEN** 数据集包含 hard 题目但映射只提供 easy 与 medium
- **THEN** 启动报错并列出未覆盖难度，不执行任何评估

#### Scenario: 参数互斥

- **WHEN** 同时提供 `--difficulty-strategy` 与 `--strategy`，或 `--budget-cap` 未伴随映射
- **THEN** 报错退出并以非零码结束

### Requirement: 运行中预算降级

系统 SHALL 支持通过 `--budget-cap USD` 设置本次任务的累计成本上限：逐题累计已知定价的调用成本，达到上限后，后续题目 SHALL 自动改用映射中最便宜策略执行，其结果 SHALL 标记 `cost_downgraded=true`；监控覆盖同一任务的完整成本，`--resume` 恢复时 SHALL 先回放已完成题目的成本再继续执行，不追溯其他运行的历史。

#### Scenario: 达上限后降级

- **WHEN** 运行中累计已知成本达到预算上限，后续仍有未执行题目
- **THEN** 后续题目全部以映射中最便宜策略执行，结果带 `cost_downgraded=true`，且已完成的题目结果不受影响

#### Scenario: 未达上限不降级

- **WHEN** 运行全程累计成本未达上限
- **THEN** 所有题目按映射策略执行，无结果被标记 `cost_downgraded`

### Requirement: 成本口径诚实呈现

成本监控 SHALL 只累计定价与用量均已知的调用成本；含未知费用的单元 SHALL 单独计数并在运行摘要中呈现。同一单元含有已知和未知调用时，已知小计仍 SHALL 纳入累计。

#### Scenario: usage 未知不虚计

- **WHEN** 同一单元有已知费用的调用，也有缺少用量或定价的调用
- **THEN** 累计只纳入已知费用，未知单元计数增加一次

### Requirement: 默认关闭且不影响既有流程

未提供映射参数时系统 SHALL 保持既有执行路径与产物格式不变；固定预算实验（experiment）SHALL 不受选择器与预算降级影响。

#### Scenario: 未启用时行为不变

- **WHEN** 不带新参数运行 `harness run` 或运行 `harness experiment`
- **THEN** 执行路径、报告与产物格式与引入本功能前一致

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

报告 SHALL 在每个难度桶呈现累计已知成本 `cost_usd`。运行摘要 SHALL 逐难度列出已知小计、未知费用单元数、预算上限与降级题数。摘要只列出有预算分配的难度。

#### Scenario: 成本分布呈现

- **WHEN** 带分配预算的运行完成
- **THEN** 报告按难度桶给出 cost_usd，摘要逐难度给出已知小计、未知单元数、预算与降级数

### Requirement: CLI 美元预算遇到未知费用时暂停

有美元预算约束的 CLI 评估 SHALL 在配置模型缺价时暂停派发；如在执行中发现模型调用费用未知，SHALL 阻止该单元的后续模型请求和重试，并暂停受该预算约束的后续派发。恢复 SHALL 重用已保存结果，并将每个单元的已知金额和未知标记累计一次。摘要 SHALL 呈现已知小计、未知单元数和预算状态；有未知费用且缺少已知金额时 SHALL 显示费用未知。

#### Scenario: 缺价或缺用量

- **WHEN** 已设置美元上限，配置模型缺价，或本次运行的实际请求返回未知费用
- **THEN** 评估在相关的下一个派发边界暂停，并标明预算无法核算

#### Scenario: 显式零价

- **WHEN** 模型有显式零价且返回已知用量
- **THEN** 单元按有效的零美元计入预算，恢复时仍只累计一次
