# reporting/chart-error-handling Specification

## Purpose
为图表生成过程提供错误处理和降级策略，确保单个图表生成失败不影响整体报告的生成和可用性。

## Requirements

### Requirement: 图表生成失败不中断报告

当单个图表生成过程抛出异常时，系统 SHALL 捕获异常并继续生成报告的其他部分，而不是完全失败。

#### Scenario: Token 图表生成失败但报告继续

- **WHEN** Token 图表生成过程中发生异常（如数据格式错误、matplotlib 渲染失败）
- **THEN** 系统捕获异常，在该图表位置显示错误信息，并继续生成其他图表和报告内容

#### Scenario: 多个图表失败时各自独立处理

- **WHEN** 成功率图表和迭代分布图都发生生成异常
- **THEN** 两个图表位置分别显示各自的错误信息，其他正常图表和报告内容正常显示

### Requirement: 错误信息清晰可追溯

图表生成失败时，系统 SHALL 在报告中显示清晰的错误提示，包含异常类型和简要描述。

#### Scenario: 显示具体错误信息

- **WHEN** 图表生成失败
- **THEN** 报告在该图表位置显示格式为 "Error generating [chart name]: [exception message]" 的错误信息

#### Scenario: 错误信息不暴露敏感路径

- **WHEN** 图表生成失败且异常包含文件系统路径
- **THEN** 显示的错误信息仅包含异常类型和简要描述，不包含完整的文件系统路径或内部实现细节

### Requirement: 图表生成器方法级别的异常处理

每个图表生成方法 SHALL 独立处理其内部异常，返回 None 或抛出明确的自定义异常，而不是让底层库异常直接传播。

#### Scenario: ChartGenerator 方法返回 None 表示失败

- **WHEN** 图表生成方法内部发生不可恢复的异常
- **THEN** 方法返回 None 而不是抛出异常，调用方通过返回值判断是否成功

#### Scenario: 调用方检查返回值处理失败情况

- **WHEN** HTMLGenerator 调用 ChartGenerator 方法且返回 None
- **THEN** HTMLGenerator 在该图表位置插入错误提示信息而不是尝试编码 None 值
