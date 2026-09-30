# Pareto Analysis Specification

## ADDED Requirements

### Requirement: 可比重复平均

系统 MUST 从已完成实验收集模型-策略配置的成本与成功计数，平均可比重复，并报告次数和范围；系统 MUST 拒绝跨不同题集、分母、预算、沙箱条件或代码版本混合分析，且多实验代码快照 MUST 来自干净工作区。

#### Scenario: 同组合重复两次

- **Given** 同一完整题集两次成本分别为 1 和 3 美元，成功率分别为 40% 和 80%
- **When** 汇总该配置组合
- **Then** 平均成本为 2 美元，平均成功率为 60%，范围与次数完整记录

#### Scenario: 未知价格重复

- **Given** 一个变体的某次重复成本未知
- **When** 分析前沿
- **Then** 整个变体被排除并记录原因，不把未知成本视为零

### Requirement: 严格非支配前沿

系统 MUST 将未被其他点在低成本和高成功率两个方向严格支配的点识别为前沿，完全相同指标点 MUST 均保留。

#### Scenario: 支配与相同点

- **Given** 两个点指标完全相同，第三点成本更高且成功率更低
- **When** 计算前沿
- **Then** 前两个点为前沿，第三点标识为被支配

### Requirement: 静态图表和预算建议

系统 MUST 提供成本为 X 轴、成功率为 Y 轴并区分前沿与非前沿的散点图，标识模型-策略配置，推荐性价比组合及各预算内最高成功率组合；建议 MUST 明示历史平均的局限。

#### Scenario: 不足预算

- **Given** 所有前沿点平均成本都超过给定预算
- **When** 生成预算建议
- **Then** 返回无可行方案，不选择超预算点

### Requirement: 自动与多实验分析

系统 MUST 在实验报告中自动保存单实验分析，并提供读取多实验目录的 CLI；分析 MUST 不调用模型或修改输入报告。

#### Scenario: 多来源分析

- **Given** 两个不同实验 ID 的完整快照确认评测条件相同
- **When** 运行 `harness pareto --experiments ... --output-dir ...`
- **Then** 输出聚合 JSON、Markdown 和 PNG，输入文件保持不变
