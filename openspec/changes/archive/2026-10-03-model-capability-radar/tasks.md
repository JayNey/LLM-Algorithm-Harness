## 1. 能力维度定义和问题分类

- [x] 1.1 创建 src/reporting/capability_profiler.py 模块，定义算法类型维度常量（Array、Graph、Dynamic Programming、Greedy、Math、String、Other）并验证模块可导入
- [x] 1.2 实现 tags 到维度的映射字典，覆盖常见 tags（如 "array"/"list" → Array, "graph" → Graph, "dp"/"dynamic-programming" → DP 等）并验证映射逻辑准确
- [x] 1.3 实现问题分类函数 classify_problem(problem: Problem) -> list[str]，根据 tags 返回所属维度列表，并验证单元测试覆盖单维度、多维度和无匹配标签场景

## 2. 能力评分计算

- [x] 2.1 实现 calculate_dimension_scores(results: list[ExecutionResult], problems: list[Problem]) -> dict[str, dict[str, float]]，按模型和维度聚合成功率，并验证单元测试覆盖成功率计算和维度无题目时返回 0.0
- [x] 2.2 实现 get_dimension_problem_counts(problems: list[Problem]) -> dict[str, int]，统计每个维度的题目数量，并验证多维度归属问题不重复计数
- [x] 2.3 添加辅助函数 normalize_score_to_100(success_rate: float) -> float 将成功率归一化为 0-100 分，并验证边界值（0.0 → 0.0, 1.0 → 100.0）

## 3. 雷达图生成

- [x] 3.1 在 ChartGenerator 类中添加 generate_capability_radar 方法签名和参数定义（接收维度评分、模型名称列表、维度名称列表），并验证方法可调用
- [x] 3.2 实现单模型雷达图绘制逻辑，使用 matplotlib polar projection，设置维度轴标签和 0-100 分网格线，并验证生成的图表包含正确的维度数量和标签
- [x] 3.3 扩展为多模型叠加支持，为不同模型使用不同颜色（蓝、橙、绿、红）和透明度（alpha=0.3 填充），添加图例，并验证多模型图表颜色区分清晰
- [x] 3.4 优化雷达图样式：设置中文字体支持、适当的图表大小（8x8 inches）、清晰的网格线和标签旋转，并验证中文维度名称显示正常
- [x] 3.5 实现返回 base64 编码的 PNG 图片字符串，复用现有 _fig_to_base64 方法，并验证返回的字符串可解码为有效 PNG

## 4. 能力分析文本生成

- [x] 4.1 实现 generate_capability_analysis(dimension_scores: dict[str, float]) -> str，识别强项（≥80）和弱项（<50）维度，并验证单元测试覆盖不同得分分布场景
- [x] 4.2 生成综合评价文本，包含各维度得分列表、强弱项总结，格式为 Markdown，并验证输出格式符合报告集成要求

## 5. HTML 报告集成

- [x] 5.1 修改 src/reporting/html_generator.py，在 generate_html_report 方法中调用 capability_profiler 计算维度评分，并验证报告生成流程不受影响
- [x] 5.2 调用 ChartGenerator.generate_capability_radar 生成单模型雷达图，将 base64 图片嵌入 HTML 报告新章节，并验证 HTML 中包含雷达图 img 标签
- [x] 5.3 添加能力分析文本章节，展示维度得分和强弱项总结，并验证文本正确渲染为 HTML
- [x] 5.4 实现无数据时的优雅降级：当所有维度题目数为 0 时跳过雷达图章节，并验证空数据场景下报告生成成功

## 6. 实验对比面板集成

- [x] 6.1 修改 src/experiment_panel.py，在面板生成逻辑中收集所有模型的维度评分数据，并验证数据结构正确
- [x] 6.2 调用 ChartGenerator.generate_capability_radar 生成多模型对比雷达图，将 base64 图片嵌入面板 HTML，并验证面板包含多模型雷达图
- [x] 6.3 添加维度题目数量标注到面板，避免误导性结论（如样本过少的维度），并验证标注信息显示清晰

## 7. 测试和文档

- [x] 7.1 为 capability_profiler 模块编写单元测试，覆盖分类、评分计算和分析文本生成，并验证 pytest 运行全部通过
- [x] 7.2 为 ChartGenerator.generate_capability_radar 编写单元测试，验证单模型和多模型场景的图表生成，并确认返回的 base64 字符串有效
- [x] 7.3 运行集成测试：使用真实评测数据生成包含雷达图的 HTML 报告和实验面板，并验证雷达图正确显示且数据准确
- [x] 7.4 更新项目文档（如有 README 或开发文档），说明新增的能力雷达图功能和使用方式，并验证文档描述清晰
