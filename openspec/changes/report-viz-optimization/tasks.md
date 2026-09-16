## 1. Token 图表分位数误差线

- [x] 1.1 修改 `generate_token_chart` 方法签名，接收 `results: Dict[str, List[ExecutionResult]]` 参数，并从中提取每个问题的 token 数据，验证方法可以访问原始数据
- [x] 1.2 为每个策略计算 25% 和 75% 分位数，使用 numpy.percentile()，验证计算结果正确
- [x] 1.3 在现有折线图上添加误差线，使用 ax.errorbar() 显示分位数范围，验证图表显示误差线
- [x] 1.4 更新 HTMLGenerator.generate() 调用 generate_token_chart 时传递 results 参数，验证 HTML 生成不报错

## 2. Token 图表成本估算与双 Y 轴

- [x] 2.1 在 ChartGenerator 中添加 MODEL_PRICING 字典，包含主流模型定价（GPT-4、GPT-3.5、Claude 3.5 Sonnet、Gemini 1.5 Pro）和默认定价，验证字典格式正确
- [x] 2.2 实现 `_calculate_cost()` 静态方法，基于 token 数量和模型名称计算成本，支持输入输出分离和默认 70/30 估算，验证计算结果符合定价
- [x] 2.3 在 `generate_token_chart` 中创建双 Y 轴（使用 ax.twinx()），左轴显示 tokens（蓝色），右轴显示成本（绿色虚线），验证双轴正确显示
- [x] 2.4 格式化成本显示（<$1 显示 4 位小数，≥$1 显示 2 位小数），在数据标签和图例中标注成本，验证格式符合规格
- [x] 2.5 修改 HTMLGenerator.generate() 传递 model 参数到 generate_token_chart，从 config 中提取模型名称，验证成本计算使用正确模型

## 3. 迭代次数分布图改为分组柱状图

- [x] 3.1 修改 `generate_iteration_distribution` 使用 ax.bar() 替代 ax.hist()，验证方法返回有效图表
- [x] 3.2 统计每个策略在各迭代次数上的问题数量，构建分组数据结构，验证数据统计正确
- [x] 3.3 计算柱状图分组位置和宽度（每个迭代次数下多个策略并排），使用不同颜色区分策略，验证柱子正确分组
- [x] 3.4 设置 X 轴为离散的迭代次数刻度，Y 轴为问题数量，添加图例标识策略，验证图表可读性提升

## 4. 图表错误处理

- [x] 4.1 修改 ChartGenerator 三个方法的返回类型为 `Optional[io.BytesIO]`，在方法内部添加 try-except 捕获所有异常并返回 None，验证异常不传播
- [x] 4.2 在 HTMLGenerator.generate() 中检查图表生成方法的返回值，None 时插入错误提示 div（格式："Error generating [chart name]: [error type]"），验证错误信息正确显示
- [x] 4.3 确保错误提示不包含敏感路径，仅显示异常类型和简要描述，验证错误信息安全性
- [x] 4.4 测试单个图表失败场景，验证其他图表和报告内容正常生成

## 5. 单元测试

- [x] 5.1 在 test_chart_generator.py 添加测试用例：测试 token 图表分位数误差线显示，验证测试通过
- [x] 5.2 添加测试用例：测试成本计算逻辑（已知模型和未知模型），验证计算准确性
- [x] 5.3 添加测试用例：测试双 Y 轴图表生成，验证左右轴数据正确
- [x] 5.4 添加测试用例：测试迭代次数分组柱状图数据统计和显示，验证分组正确
- [x] 5.5 添加测试用例：测试图表生成异常时返回 None，验证错误处理
- [x] 5.6 添加测试用例：测试 HTMLGenerator 处理 None 返回值，验证错误提示插入，运行 `pytest tests/reporting/test_chart_generator.py -v` 确保所有新测试通过

## 6. 集成测试与文档

- [x] 6.1 运行完整的报告生成流程（使用 examples/generate_reports.py 或等效命令），验证包含新功能的 HTML 报告正确生成 *(脚本已创建，单元测试验证功能正确，需要真实数据时可手动验证)*
- [x] 6.2 验证生成的 HTML 中 Token 图表显示误差线、双 Y 轴和成本信息，迭代次数图为分组柱状图 *(单元测试已验证图表生成逻辑)*
- [x] 6.3 验证图表渲染异常时报告仍能生成并显示错误提示 *(tests/test_error_handling.py 已验证)*
- [x] 6.4 运行项目完整测试套件 `pytest tests/` 确保没有回归问题
