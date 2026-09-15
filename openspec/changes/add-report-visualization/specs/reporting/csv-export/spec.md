## Purpose

提供将评测结果导出为 CSV 格式的能力，支持在 Excel 等工具中进行数据分析和处理。

## ADDED Requirements

### Requirement: 导出执行结果为 CSV

系统 SHALL 将 ExecutionResult 列表导出为结构化的 CSV 文件，包含所有关键指标。

#### Scenario: 成功导出单个策略结果
- **WHEN** 用户调用 CSVExporter.export() 并传入一个策略的结果列表和输出路径
- **THEN** 系统在指定路径生成 CSV 文件，包含 problem_id、strategy、status、passed、tokens、time、iterations 列

#### Scenario: 导出多个策略结果
- **WHEN** 用户调用 CSVExporter.export_all() 并传入多个策略的结果字典
- **THEN** 系统生成单个 CSV 文件，包含所有策略的结果，每行代表一个 problem-strategy 组合

#### Scenario: 处理空结果列表
- **WHEN** 用户传入空的结果列表
- **THEN** 系统生成仅包含表头的 CSV 文件

### Requirement: CSV 格式规范

生成的 CSV 文件 SHALL 符合标准格式，确保跨平台兼容性。

#### Scenario: UTF-8 编码
- **WHEN** 生成 CSV 文件
- **THEN** 文件使用 UTF-8 编码，包含 BOM 标记以确保 Excel 正确识别

#### Scenario: 字段转义
- **WHEN** 字段内容包含逗号、换行符或引号
- **THEN** 系统正确转义这些特殊字符，使用双引号包裹字段

### Requirement: 数据完整性

导出的 CSV SHALL 保留原始结果的所有关键信息，不丢失数据。

#### Scenario: 保留失败信息
- **WHEN** ExecutionResult 包含 error_message
- **THEN** CSV 包含 error_message 列，保留完整错误信息

#### Scenario: 保留测试用例详情
- **WHEN** ExecutionResult 包含多个 test_results
- **THEN** CSV 包含 total_tests、passed_tests、failed_tests 汇总列
