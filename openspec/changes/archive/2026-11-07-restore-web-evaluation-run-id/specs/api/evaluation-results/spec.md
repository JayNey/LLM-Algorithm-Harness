## MODIFIED Requirements

### Requirement: 所有者范围内的结果查询

系统 SHALL 提供评估结果详情、分页列表和单题历史。调用方 MUST 已认证。路径中的运行标识 SHALL 匹配该用户的 `evaluations.id`、`evaluations.run_id` 或系统为其历史评估提供的兼容标识。其他用户的运行 SHALL 返回 404，列表 SHALL NOT 包含其他用户的数据。列表 SHALL 分页，并支持按策略、难度、标签和状态过滤。详情中的策略汇总 SHALL 覆盖该次运行的全部单元，并包含 `avg_execution_time`；题目列表 SHALL 只返回当前页。

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

#### Scenario: 执行中的 Web 评估获得稳定的公开运行标识

- **WHEN** Web 评估进入执行，随后重新读取结果详情或恢复同一次评估
- **THEN** 系统 SHALL 持久化并返回同一公开 `run_id`，所有者可用该标识读取结果、下载三种报告及查询单次分析

#### Scenario: 历史评估缺少运行标识

- **WHEN** 所有者读取已有落库单元但缺少 `run_id` 的历史评估
- **THEN** 详情 SHALL 返回稳定的兼容标识，结果、报告与分析 SHALL 能用该标识访问已落库单元
- **AND** 其他账号使用该标识访问时 SHALL 收到 404
