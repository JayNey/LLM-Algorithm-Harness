## Why

文档中描述了完整的报告和可视化系统（MetricsCalculator、ReportGenerator），但实际代码中仅实现了基础的 JSON 输出和终端文本报告。研究人员和评估人员需要更丰富的可视化报告来分析策略表现、对比结果和识别失败模式，这是项目规格中"生成标准化评测报告"和"趋势分析报告"需求的关键组件。

## What Changes

- **新增 CSV 导出模块**：将 ExecutionResult 导出为结构化表格，支持 Excel 分析
- **新增 Markdown 报告生成器**：汇总评测指标，生成可读性强的文本报告
- **新增图表生成模块**：使用 matplotlib 生成三种核心图表
  - 成功率对比柱状图：横向对比各策略表现
  - Token 消耗折线图：展示策略的资源效率
  - 迭代次数分布图：分析多轮策略的收敛特性
- **新增 HTML 报告生成器**：生成自包含的 HTML 报告，内嵌图表为 Base64 图片

**约束**：
- 不修改现有的 `harness.py`、`models.py`、`strategies/` 等核心评测逻辑
- 新增模块独立可测，提供完整单元测试
- 保持与现有 JSON 输出的兼容性

## Capabilities

### New Capabilities

- `reporting/csv-export`: CSV 格式的结果导出能力
- `reporting/markdown-generation`: Markdown 格式报告生成能力  
- `reporting/chart-generation`: 基于 matplotlib 的图表生成能力
- `reporting/html-generation`: 自包含 HTML 报告生成能力

### Modified Capabilities

<!-- 无需修改现有 capability 的 requirements -->

## Impact

**新增文件**：
- `src/reporting/__init__.py`
- `src/reporting/csv_exporter.py`
- `src/reporting/markdown_generator.py`
- `src/reporting/chart_generator.py`
- `src/reporting/html_generator.py`
- `tests/test_csv_exporter.py`
- `tests/test_markdown_generator.py`
- `tests/test_chart_generator.py`
- `tests/test_html_generator.py`

**修改文件**：
- `src/main.py`：集成报告生成调用（可选，提供独立 CLI 入口）
- `requirements.txt`：新增 matplotlib、pandas 依赖

**依赖变更**：
- 新增：`matplotlib>=3.7.0`
- 新增：`pandas>=2.0.0`（用于 CSV 导出）

**对现有功能的影响**：
- 零影响：报告模块完全独立，现有评测流程不受影响
- 向后兼容：保留现有 JSON 输出机制
