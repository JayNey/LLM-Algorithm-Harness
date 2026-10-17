# api/evaluation-results Specification

## Purpose
TBD - created by archiving change evaluation-results-api. Update Purpose after archive.

## Requirements

### Requirement: 所有者范围内的结果查询

系统 SHALL 提供评估结果详情、分页列表和单题历史。调用方 MUST 已认证。路径中的运行标识 SHALL 匹配该用户的 `evaluations.id` 或 `evaluations.run_id`。其他用户的运行 SHALL 返回 404，列表 SHALL NOT 包含其他用户的数据。列表 SHALL 分页，并支持按策略、难度、标签和状态过滤。详情中的策略汇总 SHALL 覆盖该次运行的全部单元，并包含 `avg_execution_time`；题目列表 SHALL 只返回当前页。

#### Scenario: 按运行标识读取本人的任务结果

- **WHEN** 用户请求自己某次已完成评估的结果详情
- **THEN** 响应包含该次运行的状态、时间、覆盖全部单元的策略汇总，以及当前页的题目摘要

#### Scenario: 详情分页不截断策略汇总

- **WHEN** 用户以小于单元总数的 limit 请求自己某次运行的详情
- **THEN** 每个策略汇总仍覆盖该策略的全部单元并包含 `avg_execution_time`，题目列表只含当前页，分页总数等于全部单元数

#### Scenario: 他人运行不可见

- **WHEN** 用户使用另一个用户的 evaluation id 或 run_id 请求结果
- **THEN** 响应为 404，且列表接口不返回该运行

#### Scenario: 按标签过滤结果列表

- **WHEN** 用户按某个题目标签过滤自己的结果
- **THEN** 只返回至少包含一个匹配单元的运行，分页总数等于这些运行的数量

### Requirement: 统计口径与落库结果一致

系统 SHALL 从已落库单元计算成功率、token、执行时间和失败模式。成功率的分母 SHALL 为参与统计的单元数，分子 SHALL 为 `status == "success"` 的单元数。`cost_unknown` 的单元 SHALL NOT 被计入美元合计，响应 SHALL 标出其数量。迭代统计 SHALL 只聚合 `metrics.iterations`；该字段缺失时 SHALL 视为未知，不得用 0 或 1 代替。

#### Scenario: 成功与失败混合时的成功率

- **WHEN** 一次运行有 3 个成功单元和 1 个失败单元
- **THEN** 成功率统计为 0.75，成功数为 3，总数为 4

#### Scenario: 未知成本不计入美元合计

- **WHEN** 一个单元标记 `cost_unknown`，另一个单元的 `cost_usd` 为 0.2
- **THEN** 美元合计为 0.2，且响应标出 1 个成本未知的单元

#### Scenario: 缺少迭代次数字段

- **WHEN** 历史结果行的 metrics 没有 `iterations`
- **THEN** 迭代统计把该单元计为未知，不把它显示为 0 次迭代

### Requirement: 新结果记录迭代次数

系统 SHALL 在新写入的单元 metrics 中保存 `iterations`，其值等于该单元执行轨迹的长度；没有轨迹时为 0。系统 SHALL NOT 为了该字段保存生成代码、沙箱输出或模型原文。

#### Scenario: 多轮策略记下迭代次数

- **WHEN** 一个单元以 2 轮轨迹结束并被写入结果表
- **THEN** 该行 `metrics.iterations` 为 2

### Requirement: 对比使用同一聚合

策略对比、模型对比和历史对比 SHALL 使用与单次结果详情相同的成功率和成本聚合。历史对比 SHALL 只包含该用户、同一模型与同一策略集合下的已完成运行，并按完成时间排列。A/B 对比 SHALL 返回该用户已有 A/B 测试结果；测试不存在或不属于该用户时 SHALL 返回 404。

#### Scenario: 策略对比与详情一致

- **WHEN** 用户对比同一次运行中的两个策略
- **THEN** 每个策略的成功率、解出数和成本与该运行详情中的对应汇总值相同

#### Scenario: 没有历史时返回空序列

- **WHEN** 用户请求一个尚无其他已完成运行的配置的历史对比
- **THEN** 响应成功且对比序列为空，而不是错误

### Requirement: 可视化数据来自同一统计

系统 SHALL 为成功率、token、能力雷达、成本-准确率和学习曲线返回 JSON 数据。能力雷达的维度顺序和 0–100 分 SHALL 来自现有能力画像计算；没有对应题目的维度分数为 0，并单独给出各维度题目数。学习曲线没有基准运行时 SHALL 返回空序列。

#### Scenario: 雷达维度与题目数

- **WHEN** 用户请求自己某次运行的能力雷达数据
- **THEN** `dimensions` 的顺序与能力画像的预定义维度一致，`series` 中的分数在 0 到 100 之间，`problem_counts` 给出每个维度的题目数

#### Scenario: 空学习曲线

- **WHEN** 用户没有任何已完成的基准运行
- **THEN** 学习曲线接口返回 200 和空序列

### Requirement: 失败分析不重建隐藏证据

失败汇总、按标签的弱项和失败案例 SHALL 只使用结果行上的状态、`failure_mode`、`failure_category` 和 `error_message`，以及题库中的难度与标签。错误信息聚类 SHALL 使用现有错误分析的归一化规则。系统 SHALL NOT 读取隐藏测试输入或未落库的沙箱轨迹来补充分类。

#### Scenario: 按已保存的失败模式汇总

- **WHEN** 一次运行的失败单元已经保存了 `failure_mode`
- **THEN** 失败汇总按这些模式计数，且不因缺少沙箱轨迹而改写模式

#### Scenario: 失败案例只包含失败单元

- **WHEN** 用户请求某次运行的失败案例
- **THEN** 列表只包含非成功单元，并带有已保存的错误信息；成功单元不出现

### Requirement: 报告导出与统计一致

系统 SHALL 为该用户的一次运行导出 Markdown、CSV 和 HTML。导出中的成功率、解出数、token 和成本 SHALL 与同一运行的 JSON 统计相同。CSV SHALL 使用与现有 CSV 导出相同的列；未落库的测试计数和缺失的 `iterations` SHALL 留空，不得写成 0 或 1。PNG SHALL 只在现有图表生成器支持该图时返回图片字节；不支持的图 SHALL 返回明确错误，而不是空图片。

#### Scenario: CSV 缺失字段留空

- **WHEN** 导出的单元没有测试计数，或历史行的 metrics 没有 `iterations`
- **THEN** 对应 CSV 单元格为空

#### Scenario: Markdown 与 JSON 的成功率相同

- **WHEN** 用户先读取某次运行的 JSON 统计，再导出该运行的 Markdown
- **THEN** 两处的总体成功率和解出数相同

#### Scenario: 他人运行不能导出

- **WHEN** 用户请求另一个用户运行的 CSV
- **THEN** 响应为 404，且不返回文件内容
