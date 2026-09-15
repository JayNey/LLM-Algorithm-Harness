## Why

已有的报告可视化模块（add-report-visualization）完成了基础框架，但在实际使用中发现四个高优先级问题影响研究人员的数据分析效率：Token 图表缺少误差展示、成本估算未可视化、图表渲染异常未处理、迭代分布图不够直观。这些改进将增强报告的分析价值和鲁棒性。

## What Changes

- **Token 图表增加分位数误差线**：在现有折线图基础上添加 25%/75% 分位数误差带，帮助识别 Token 消耗的波动范围
- **Token 图表增加成本估算**：使用双 Y 轴显示 Token 数量（左轴）和对应美元成本（右轴），支持可配置的单价
- **HTML 报告增强错误处理**：为图表渲染添加 try-catch，失败时显示占位符而非整体崩溃
- **迭代次数分布改为分组柱状图**：将直方图改为按策略分组的柱状图，更清晰对比不同策略的迭代分布

**约束**：
- 只修改 `src/reporting/` 模块，不触及 Judge、Problem、TestCase 等核心评测代码
- 保持向后兼容，现有报告生成接口签名不变
- 新增功能配套完整单元测试

## Capabilities

### New Capabilities

<!-- 无新增 capability，均为现有 reporting 能力的增强 -->

### Modified Capabilities

- `reporting/chart-generation`: 增加 Token 图表的误差线和双 Y 轴成本显示功能；改进迭代分布图为分组柱状图
- `reporting/html-generation`: 增加图表渲染异常处理，提升鲁棒性

## Impact

**修改文件**：
- `src/reporting/chart_generator.py`：增强 `generate_token_chart()` 和 `generate_iteration_distribution()` 方法
- `src/reporting/html_generator.py`：在图表嵌入处增加异常处理
- `tests/reporting/test_chart_generator.py`：新增误差线、双轴、分组柱状图的测试用例
- `tests/reporting/test_html_generator.py`：新增图表渲染异常处理的测试用例

**新增文件**：
- `openspec/specs/reporting/chart-generation/delta-spec.md`：描述 Token 图表和迭代分布图的增强需求
- `openspec/specs/reporting/html-generation/delta-spec.md`：描述 HTML 报告的错误处理需求

**依赖变更**：
- 无新增依赖（继续使用现有的 matplotlib 和 pandas）

**对现有功能的影响**：
- 向后兼容：现有调用方式无需修改
- 增强鲁棒性：图表生成失败不再导致整个 HTML 报告生成失败
- 数据展示更丰富：新增误差线和成本估算帮助更全面分析结果
