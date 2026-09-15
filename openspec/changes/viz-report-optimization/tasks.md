## 1. Token 图表增强 - 分位数误差线

- [x] 1.1 在 `chart_generator.py` 的 `generate_token_chart()` 中添加 `show_percentiles` 参数（默认 False），验证现有测试不受影响
- [x] 1.2 实现 Token 消耗的 25%/75% 分位数计算逻辑，验证使用 `numpy.percentile()` 正确计算各策略的分位数
- [x] 1.3 使用 `ax.fill_between()` 绘制半透明误差带（alpha=0.2），验证误差带颜色与主折线匹配
- [x] 1.4 在 `test_chart_generator.py` 中新增测试用例验证分位数误差线正确显示，包括边界情况（样本量 < 5）

## 2. Token 图表增强 - 成本估算双轴

- [ ] 2.1 在 `generate_token_chart()` 中添加 `token_cost_per_1k` 参数（默认 0.01），验证参数类型为 float
- [ ] 2.2 使用 `ax.twinx()` 创建右侧 Y 轴显示美元成本，验证右轴刻度与左轴 Token 数同步
- [ ] 2.3 为右轴添加标签和图例，格式为 "Cost (USD, $X.XX/1K tokens)"，验证图例清晰区分 Token 轴和成本轴
- [ ] 2.4 在 `test_chart_generator.py` 中新增测试用例验证双轴显示正确，包括不同成本单价配置

## 3. 迭代分布图改进 - 分组柱状图

- [ ] 3.1 重构 `generate_iteration_distribution()` 从直方图改为分组柱状图，验证多策略数据正确分组
- [ ] 3.2 实现动态柱宽计算（`width / num_strategies`），验证柱子不重叠且间距合理
- [ ] 3.3 为每个策略分配不同颜色并添加图例，验证图例与柱子颜色对应
- [ ] 3.4 实现动态图表宽度调整（策略数 > 5 时增加宽度），验证 `figsize[0] = max(10, num_strategies * 2)`
- [ ] 3.5 在 `test_chart_generator.py` 中新增测试用例验证分组柱状图正确显示，包括单策略、多策略（2-6个）场景

## 4. HTML 报告错误处理增强

- [ ] 4.1 在 `html_generator.py` 的图表生成调用处添加 try-except 包装，验证每个图表调用都有异常处理
- [ ] 4.2 实现占位符 HTML 生成函数 `_generate_chart_error_placeholder(error, chart_name)`，验证占位符包含错误类型和图表名称
- [ ] 4.3 集成占位符到 HTML 模板中，验证失败图表位置显示占位符而非空白
- [ ] 4.4 在 `test_html_generator.py` 中新增测试用例模拟图表生成失败，验证 HTML 报告仍能完整生成且包含占位符

## 5. 向后兼容性验证

- [ ] 5.1 运行现有的 `test_chart_generator.py` 全部测试，验证新增参数不影响现有默认行为
- [ ] 5.2 运行现有的 `test_html_generator.py` 全部测试，验证异常处理不影响正常报告生成
- [ ] 5.3 使用 `examples/generate_reports.py` 脚本测试新功能，验证误差线、成本轴、分组柱状图正确显示

## 6. 文档更新

- [ ] 6.1 更新 `src/reporting/chart_generator.py` 的 docstring，说明新增参数的用途和默认值
- [ ] 6.2 更新 `examples/generate_reports.py` 添加新功能的使用示例
- [ ] 6.3 在 OpenSpec change 目录中创建 `IMPLEMENTATION_SUMMARY.md`，记录本次改动的关键决策和验证结果
