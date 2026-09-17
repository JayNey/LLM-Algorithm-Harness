## Why

当前报告可视化模块缺少关键的数据展示功能，影响评测结果的可读性和分析深度。具体问题包括：Token 图表缺少误差线和成本信息、图表渲染异常缺少错误处理、迭代次数分布图展示不够清晰。这些改进将提升报告的信息密度和可靠性。

## What Changes

- Token 图表增加分位数（25%、75%）误差线，展示 token 消耗的分布范围
- Token 图表增加成本估算功能，使用双 Y 轴同时展示 token 数量和成本
- HTML 报告增加图表渲染异常的 try-catch 错误处理，防止单个图表失败导致整个报告生成中断
- 迭代次数分布图从重叠的直方图改为分组柱状图，提升多策略对比的可读性

## Capabilities

### New Capabilities

- `reporting/chart-error-handling`: 图表生成的错误处理和降级策略，确保单个图表失败不影响整体报告生成
- `reporting/token-cost-estimation`: Token 成本估算能力，基于模型定价计算评测成本

### Modified Capabilities

无现有 spec 需要修改。本次变更是对现有可视化模块的功能增强，不涉及已有规格的需求变更。

## Impact

**受影响的代码：**
- `src/reporting/chart_generator.py`: 修改 `generate_token_chart()` 和 `generate_iteration_distribution()` 方法
- `src/reporting/html_generator.py`: 增强图表渲染的错误处理逻辑

**受影响的测试：**
- `tests/reporting/test_chart_generator.py`: 需要新增测试用例覆盖新功能

**不影响：**
- 核心评测逻辑（Judge、Problem、TestCase）
- 其他报告格式（Markdown、CSV）
- 现有 API 接口和数据结构
