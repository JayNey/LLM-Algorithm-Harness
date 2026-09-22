# experiment/budget-comparison Specification

## Purpose
在固定计算预算下对比模型与策略：支持模型×策略×题集×重复编号的实验组合，按每题调用数 / token / 耗时预算控制执行，记录可复现元数据，并输出口径一致、可复核的对比报告。

## Requirements

### Requirement: 实验配置与可复现记录

系统 SHALL 支持通过配置文件定义模型 × 策略 × 题集 × 重复编号的实验组合，并在实验结果中记录可复现元数据。

#### Scenario: 实验配置驱动执行

- **WHEN** 用户运行 `harness experiment --config experiment.json`，配置中定义了 1 个模型、2 个策略、1 个题集、2 次重复
- **THEN** 系统按 2 个策略 × 2 次重复共 4 个组合依次执行，并为每个组合生成独立结果

#### Scenario: 记录可复现元数据

- **WHEN** 实验完成并落盘
- **THEN** 实验记录包含题集文件 SHA-256 与确定的题目 ID 列表、代码版本（git commit）、每个组合的有效模型参数（温度等）、预算定义与定价快照（含来源与日期）

#### Scenario: 相同配置可重建实验

- **WHEN** 使用相同配置与题集重新运行同一实验
- **THEN** 新实验结果与原实验的目录结构、分母口径和元数据字段一致，且元数据足以人工核对两次实验的输入等价性

### Requirement: 每题预算控制与停止

系统 SHALL 为每道题支持调用数 / token / 耗时三类预算，达到预算后不再发起模型调用，并记录停止原因与实际消耗。

#### Scenario: 调用数预算耗尽

- **WHEN** 某题的预算为 3 次调用且第 3 次调用后仍未通过
- **THEN** 系统不再为该题发起新调用，该题记录停止原因 `budget_exhausted` 与已发生的调用数、token 与耗时

#### Scenario: token 预算按已知用量结算

- **WHEN** 某题的 token 预算在多轮执行中被累计用量耗尽
- **THEN** 系统在发起下一次调用前停止，累计值包含输入、输出及供应商返回的推理 token

#### Scenario: 供应商无用量数据时标注不支持硬 token 预算

- **WHEN** 模型响应不包含 usage 数据且实验声明了硬 token 预算
- **THEN** 系统在实验记录中标注该组合 `token_budget_unsupported`，不得宣称满足严格 token 预算

### Requirement: 同预算策略对比口径

系统 SHALL 在相同预算约束下对比基础单次生成与多轮策略，并报告各组合的实际消耗。

#### Scenario: 基线与多轮策略同预算对比

- **WHEN** 基线单次生成与多轮修复策略在相同题集、相同每题预算下运行
- **THEN** 对比报告同时给出两者的通过类指标与实际平均调用数、token、耗时

### Requirement: 预算内未完成题目的分母处理

系统 SHALL 将因预算耗尽而未完成的题目计入明确的未完成清单，不得从分母中静默丢弃。

#### Scenario: 组合中存在预算耗尽题目

- **WHEN** 某组合有 10 题、其中 2 题因预算耗尽未完成
- **THEN** 该组合报告显示总数 10、完成 8、未完成 2 及各自占比，通过率同时给出按总题数与按完成题数两种口径

### Requirement: 对比报告输出

系统 SHALL 输出 JSON、CSV 与可阅读的 Markdown 对比报告，包含隐藏测试通过率、样例验证率、失败类型分布、修复率、耗时与 token，以及按难度与标签的统计；重复实验给出不确定性说明。

#### Scenario: 报告包含核心指标

- **WHEN** 实验完成并生成报告
- **THEN** 报告按组合给出隐藏测试通过率、样例验证率、失败类型分布（wrong_answer、code_extraction_failed、model_error、system_error、budget_exhausted）、修复率与平均耗时 / token

#### Scenario: 按难度与标签统计

- **WHEN** 题集包含难度与标签字段
- **THEN** 报告按难度与标签分组给出各组合的通过率与样本数

#### Scenario: 重复实验的不确定性说明

- **WHEN** 同一组合重复运行超过 1 次
- **THEN** 报告给出各指标的跨重复范围（最小值 / 最大值），不宣称为位级复现

#### Scenario: 未配置定价显示未知

- **WHEN** 实验使用的模型没有可用定价
- **THEN** 报告成本列显示"未知"，不显示 $0

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
