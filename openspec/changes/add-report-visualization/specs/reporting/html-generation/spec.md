## Purpose

生成自包含的 HTML 格式评测报告，内嵌图表和样式，可在浏览器中直接查看无需外部依赖。

## ADDED Requirements

### Requirement: 生成自包含 HTML 报告

系统 SHALL 生成单个 HTML 文件，包含所有报告内容、图表和样式。

#### Scenario: 基础 HTML 结构生成
- **WHEN** 用户调用 HTMLGenerator.generate() 并传入策略指标和结果
- **THEN** 系统生成符合 HTML5 规范的文件，包含完整的 DOCTYPE、head 和 body 结构

#### Scenario: 内嵌 CSS 样式
- **WHEN** 生成 HTML 报告
- **THEN** 所有样式通过 `<style>` 标签内嵌在 `<head>` 中，无外部 CSS 依赖

#### Scenario: 响应式布局
- **WHEN** 在不同屏幕尺寸下查看报告
- **THEN** 内容使用响应式布局，在桌面和移动设备上均可正常显示

### Requirement: 内嵌图表为 Base64 图片

系统 SHALL 将 matplotlib 生成的图表转换为 Base64 编码并内嵌到 HTML 中。

#### Scenario: 图表转换和嵌入
- **WHEN** 生成 HTML 报告
- **THEN** 系统将成功率柱状图、Token 折线图、迭代分布图转换为 Base64 编码的 PNG，通过 `data:image/png;base64,` URI 嵌入 `<img>` 标签

#### Scenario: 图表缺失时的处理
- **WHEN** 某个图表生成失败或数据不足
- **THEN** 对应位置显示占位符和错误提示，不影响其他内容的显示

### Requirement: 包含交互式指标摘要

报告 SHALL 包含可折叠的指标摘要部分，提升用户体验。

#### Scenario: 策略摘要卡片
- **WHEN** 显示策略指标
- **THEN** 每个策略显示为独立的卡片，包含核心指标（成功率、Token、时间）和颜色编码的状态标识

#### Scenario: 可折叠的详细信息
- **WHEN** 用户点击 "Details" 按钮
- **THEN** 展开显示该策略的按难度分层统计、失败问题列表和迭代统计

#### Scenario: 表格排序功能
- **WHEN** 用户点击表格列标题
- **THEN** 表格按该列升序或降序排序（使用简单的 JavaScript 实现）

### Requirement: 元数据和导出信息

报告 SHALL 包含完整的元数据，便于追溯和归档。

#### Scenario: 报告头部信息
- **WHEN** 生成 HTML 报告
- **THEN** 顶部显示报告标题、生成时间、评测配置（LLM 模型、温度、超时）、问题总数

#### Scenario: 版本信息
- **WHEN** 生成报告
- **THEN** 页脚包含 Harness 版本号、Python 版本、依赖库版本

#### Scenario: 导出原始数据链接
- **WHEN** 生成 HTML 报告时同时生成了 CSV 和 JSON
- **THEN** 报告包含指向这些文件的相对链接，方便用户下载原始数据

### Requirement: HTML 格式规范

生成的 HTML SHALL 符合 Web 标准，确保跨浏览器兼容性。

#### Scenario: 有效的 HTML5 标记
- **WHEN** 使用 W3C HTML 验证器检查生成的报告
- **THEN** 无错误和警告（允许信息级提示）

#### Scenario: 字符编码
- **WHEN** 生成 HTML 文件
- **THEN** 使用 UTF-8 编码，`<meta charset="UTF-8">` 标签位于 `<head>` 开头

#### Scenario: JavaScript 安全
- **WHEN** 报告包含 JavaScript 代码（如表格排序）
- **THEN** 不使用 `eval()` 或 `innerHTML` 处理用户数据，避免 XSS 风险
