# problem-recommendation Specification

## Purpose

在既有弱项推荐（失败率分组识别、按标签推荐未评估题目、推荐理由、导出数据集）之上，推荐列表 SHALL 体现难度梯度、估算练习成本并呈现预期提升的能力维度，帮助用户循序渐进地针对弱项练习。

## ADDED Requirements

### Requirement: 难度梯度排序

推荐列表 SHALL 在相关度入选逻辑（弱项匹配与失败率排序、limit 截断）不变的前提下，按难度从易到难稳定排序输出（easy → medium → hard，同难度内保持相关度顺序，无难度标注的题目排在最后）。

#### Scenario: 从易到难输出

- **WHEN** 入选的推荐题包含 easy、hard 与未标注难度的题目
- **THEN** 输出顺序为 easy 在前、hard 居中、未标注最后，同难度内相关度顺序保持

### Requirement: 练习成本估算

每条推荐 SHALL 给出估算练习成本：优先取该题历史记录的已知定价成本均值，回退到同难度题目的均值，均无数据时 SHALL 标注为未知；成本只累计定价与 usage 已知的调用（usage/pricing 未知不计入、单独呈现）；推荐报告 SHALL 给出推荐集的总估算成本与未知成本的题目数。

#### Scenario: 成本回退链

- **WHEN** 某推荐题自身无历史成本而同难度题目有
- **THEN** 该题成本采用同难度均值；若难度级亦无数据则标注未知

#### Scenario: 总估算与未知呈现

- **WHEN** 推荐完成
- **THEN** 报告给出总估算成本（仅合计已知部分）与未知成本题数

### Requirement: 预期提升维度

每条推荐 SHALL 输出其匹配的弱项标签维度（`expected_improvement_dimensions`）；推荐报告 SHALL 汇总本次推荐覆盖的能力维度集合（`covered_dimensions`）。

#### Scenario: 维度提取与汇总

- **WHEN** 推荐题匹配多个弱项标签分组
- **THEN** 该题的维度含这些标签名，报告的覆盖维度为全部推荐的并集
