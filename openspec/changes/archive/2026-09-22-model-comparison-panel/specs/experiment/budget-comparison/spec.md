# experiment/budget-comparison Delta

## ADDED Requirements

### Requirement: 模型胜率矩阵

系统 SHALL 在同一策略下对模型两两逐题配对，输出胜/平/负计数与比率；配对基于每题的最终结果（重复实验按题取多数结果），双方同果计为平局。

#### Scenario: 胜率矩阵计算正确

- **WHEN** 模型 A 与模型 B 在同策略、8 道题的同题集下运行，A 过 B 挂 3 题、B 过 A 挂 1 题、双方同果 4 题
- **THEN** A 对 B 的单元格记录胜 3 平 4 负 1，分母为题目总数 8，且胜平负之和等于题目总数

#### Scenario: 预算未完成题参与配对

- **WHEN** 某题在模型 A 下 `budget_exhausted`、在模型 B 下通过
- **THEN** 该题计为 B 胜；双方均为 `budget_exhausted` 计为平局

### Requirement: 统计显著性差异标注

系统 SHALL 对模型两两配对的胜负计数执行 McNemar 检验，在对比报告中给出 p 值与显著性标注；不一致对数不足以检验时明确标注，不得虚构显著性。

#### Scenario: 差异显著时标注

- **WHEN** 模型 A 对 B 的不一致对（A 过 B 挂 / B 过 A 挂）计数使 McNemar p 值小于 0.05
- **THEN** 报告在该对比上标注"显著（p<0.05）"并给出具体 p 值

#### Scenario: 样本不足时明确标注

- **WHEN** 不一致对总数为 0 或过小导致检验无意义
- **THEN** 报告标注"样本不足，无法检验"，不给出显著性结论

### Requirement: 成本效益分析

系统 SHALL 按模型给出准确率/成本比排名；成本未知的模型标注"未知"并排除出排名，不显示 $0。

#### Scenario: 成本已知模型参与排名

- **WHEN** 两个模型定价已知且完成实验
- **THEN** 报告给出各自每美元通过题数并按比值排名

#### Scenario: 成本未知模型不参与排名

- **WHEN** 某模型定价未配置
- **THEN** 该模型成本效益显示"未知"且不出现在排名中

### Requirement: 交互式 HTML 对比面板

系统 SHALL 生成 `panel.html` 交互式面板：使用前端图表库（Chart.js/Plotly，CDN 引入）渲染至少三种图表——雷达图（多维度能力）、散点图（成本 vs 准确率）、柱状图（并排指标），并以表格呈现胜率矩阵；图表数据以 JSON 内嵌，离线打开时给出降级提示。

#### Scenario: 面板包含图表与矩阵

- **WHEN** 实验完成并生成面板
- **THEN** `panel.html` 包含雷达图、散点图、柱状图三种图表的数据与渲染代码，以及完整胜率矩阵表格

#### Scenario: 成本未知不进入散点图

- **WHEN** 某模型成本未知
- **THEN** 该模型不出现在成本散点图中，面板标注其成本未知

### Requirement: 组合粒度并行执行

实验配置 SHALL 支持 `execution: serial | parallel`（默认 serial）；parallel 时按 (模型, 策略, 重复) 组合粒度并行执行，每个组合持有独立的 harness 与预算追踪器；并行与串行产出的组合数据结构一致。

#### Scenario: 并行执行结果与串行一致

- **WHEN** 相同配置分别以 serial 与 parallel 执行
- **THEN** 两者生成的组合集合、每组合 summary 与 budget ledger 字段结构一致

#### Scenario: 并行度受配置约束

- **WHEN** 配置 `execution: parallel` 且组合数超过 max_workers
- **THEN** 同时执行的组合数不超过 max_workers
