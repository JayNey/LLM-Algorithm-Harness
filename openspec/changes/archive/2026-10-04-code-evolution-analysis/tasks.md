## 1. 扩展数据模型

- [x] 1.1 在 `src/models.py` 的 `IterationResult` 模型中添加 `code_quality: CodeQualityMetrics | None` 字段，并验证模型可以正常导入和序列化
- [x] 1.2 添加单元测试验证 `IterationResult` 的向后兼容性（加载不含 `code_quality` 字段的旧数据）

## 2. 创建演化分析模块

- [x] 2.1 创建 `src/analysis/` 目录和 `__init__.py`，验证模块可正常导入
- [x] 2.2 实现 `src/analysis/evolution.py` 中的 `EvolutionAnalyzer` 类骨架（包含 `__init__` 和空方法），验证类可被实例化
- [x] 2.3 实现 `EvolutionAnalyzer.identify_quality_drops()` 方法，使用阈值策略识别质量下降迭代，并添加单元测试验证下降点识别逻辑
- [x] 2.4 实现 `EvolutionAnalyzer.analyze_drop_reason()` 方法，应用规则化启发式分析下降原因，并添加单元测试覆盖各类下降模式
- [x] 2.5 实现 `EvolutionAnalyzer.generate_evolution_chart()` 方法，使用 matplotlib 生成趋势图表，并验证生成的 PNG 文件存在且格式正确
- [x] 2.6 实现 `EvolutionAnalyzer.generate_evolution_report()` 方法，生成文本格式的演化分析报告，并验证报告包含所有必需章节

## 3. 集成质量指标计算

- [x] 3.1 修改 `src/strategies/multi_round_feedback.py` 的 `execute()` 方法，在每轮迭代提取代码后调用代码质量分析，并验证质量指标被正确存储在 `IterationResult` 中
- [x] 3.2 添加异常处理，确保质量分析失败不影响迭代执行，并验证质量分析错误被记录到日志而不终止实验
- [x] 3.3 添加配置选项 `enable_evolution_analysis`（默认 `true`），允许用户禁用演化分析，并验证配置生效

## 4. 扩展报告生成

- [x] 4.1 在 `src/experiment_report.py` 中添加 `_generate_evolution_section()` 方法，调用 `EvolutionAnalyzer` 生成演化分析章节，并验证方法返回正确格式的 Markdown 内容
- [x] 4.2 修改主报告生成逻辑，检测多轮策略时插入演化分析章节，并验证生成的报告包含演化图表和分析文本
- [x] 4.3 确保非多轮策略的报告不包含演化分析章节，验证单轮策略报告格式不变

## 5. 测试和验证

- [x] 5.1 创建端到端测试，运行 `MultiRoundFeedbackStrategy` 并验证生成的 `ExecutionResult` 包含完整的质量指标
- [x] 5.2 创建集成测试，验证实验报告包含演化分析章节且图表文件存在
- [x] 5.3 运行现有测试套件，确保所有测试通过且无回归

## 6. 文档和配置

- [x] 6.1 更新项目文档，说明演化分析功能的使用方法和配置选项
- [x] 6.2 添加演化分析的示例输出到文档中，展示趋势图表和报告格式
