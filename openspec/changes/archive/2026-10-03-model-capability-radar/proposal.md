## Why

目前系统缺少直观的模型能力画像，用户难以快速了解模型在不同算法领域（如数组操作、图算法、动态规划等）的表现。现有报告仅提供总体成功率，无法展示模型在各维度上的强弱分布，不利于选择合适的模型或识别模型的能力边界。

## What Changes

- 新增模型能力雷达图生成功能，按算法类型维度展示模型成功率
- 支持将问题自动归类到预定义的算法类型（数组操作、图算法、动态规划、贪心算法、数学计算、字符串处理等）
- 计算每个维度的成功率并归一化为 0-100 分
- 生成多模型对比的雷达图，支持导出为 PNG/SVG 格式
- 将雷达图嵌入到 HTML 报告和实验对比面板中

## Capabilities

### New Capabilities

- `reporting/capability-radar`: 模型能力雷达图生成 - 按算法类型维度统计模型成功率，生成雷达图可视化，支持多模型对比和报告集成

### Modified Capabilities

<!-- 本变更不修改现有 spec 的 requirements -->

## Impact

- 新增 `src/reporting/capability_profiler.py` 模块处理能力维度定义、问题分类和评分计算
- 修改 `src/reporting/chart_generator.py` 添加雷达图生成方法
- 修改 `src/reporting/html_generator.py` 和 `src/experiment_panel.py` 集成雷达图到报告
- 依赖现有的 matplotlib 库，不引入新的外部依赖
- 影响实验报告和面板的展示内容，向后兼容（无雷达图数据时不显示该部分）
