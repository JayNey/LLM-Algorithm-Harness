# cost-aware-strategy-selection Specification

## Purpose

在评估流程中提供成本敏感的策略执行方式：按题目难度映射策略，并在运行中监控已知定价成本，达到预算上限后自动降级到最便宜策略。功能默认关闭；映射基于数据集难度标注，降级为确定性阶梯规则，不保证全局最优。

## ADDED Requirements

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

成本监控 SHALL 只累计定价与 usage 已知的调用成本；usage 未知的结果不计入累计值、SHALL 单独计数并在运行摘要中呈现，不得当作零成本静默处理。

#### Scenario: usage 未知不虚计

- **WHEN** 某些结果的调用缺少 usage 数据且预算上限已设
- **THEN** 这些结果不计入累计成本，运行摘要中的 unknown 计数如实反映其数量

### Requirement: 默认关闭且不影响既有流程

未提供映射参数时系统 SHALL 保持既有执行路径与产物格式不变；固定预算实验（experiment）SHALL 不受选择器与预算降级影响。

#### Scenario: 未启用时行为不变

- **WHEN** 不带新参数运行 `harness run` 或运行 `harness experiment`
- **THEN** 执行路径、报告与产物格式与引入本功能前一致
