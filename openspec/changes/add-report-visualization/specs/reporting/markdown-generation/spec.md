## Purpose

生成结构化的 Markdown 格式评测报告，提供人类可读的指标汇总和策略对比分析。

## ADDED Requirements

### Requirement: 生成汇总报告

系统 SHALL 生成包含所有策略指标汇总的 Markdown 报告。

#### Scenario: 生成基础指标表格
- **WHEN** 用户调用 MarkdownGenerator.generate() 并传入策略指标字典
- **THEN** 系统生成包含策略名称、成功率、解决问题数、平均 Token、平均时间的 Markdown 表格

#### Scenario: 包含标题和元数据
- **WHEN** 生成报告
- **THEN** 报告包含标题、生成时间戳、评测配置摘要（模型、温度、超时等）

#### Scenario: 多策略对比
- **WHEN** 传入多个策略的指标
- **THEN** 报告按成功率降序排列策略，突出显示最佳策略

### Requirement: 按难度分层统计

系统 SHALL 在报告中展示按问题难度（easy/medium/hard）分层的成功率统计。

#### Scenario: 展示难度分层表格
- **WHEN** 策略指标包含 by_difficulty 数据
- **THEN** 报告为每个策略生成独立的难度分层表格，显示各难度级别的成功率

#### Scenario: 缺失难度数据时的处理
- **WHEN** 某个策略缺少 by_difficulty 数据
- **THEN** 该策略的难度分层部分显示 "N/A"

### Requirement: 失败案例汇总

系统 SHALL 在报告中列出失败问题的汇总信息。

#### Scenario: 列出失败问题 ID
- **WHEN** 传入包含失败结果的 ExecutionResult 列表
- **THEN** 报告包含失败问题部分，按策略分组列出失败的 problem_id

#### Scenario: 限制失败列表长度
- **WHEN** 某个策略的失败问题超过 10 个
- **THEN** 报告仅显示前 10 个，并注明 "... and X more"

### Requirement: Markdown 格式规范

生成的报告 SHALL 符合 CommonMark 规范，确保跨平台渲染一致性。

#### Scenario: 表格对齐
- **WHEN** 生成数据表格
- **THEN** 使用标准 Markdown 表格语法，数值列右对齐，文本列左对齐

#### Scenario: 特殊字符转义
- **WHEN** 内容包含 Markdown 特殊字符（如 `*`, `_`, `|`）
- **THEN** 系统正确转义这些字符，避免破坏格式
