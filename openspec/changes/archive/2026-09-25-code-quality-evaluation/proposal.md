## Why

当前评估仅关注正确性（是否通过测试），忽略代码质量维度。实际应用中，代码的时间复杂度、空间复杂度、可读性同样重要。添加代码质量评估维度可提供更全面的评价，超越单纯正确性，更符合实际工业应用场景需求，并成为差异化竞争点。

## What Changes

- 在沙箱执行器中添加性能测试能力（不同数据规模：10x, 100x, 1000x）
- 添加内存监控功能（使用 `tracemalloc` 或 `resource` 模块）
- 集成静态分析工具：`pylint`（代码质量）、`flake8`（风格检查）、`radon`（圈复杂度）
- 在 HTML 报告中新增"代码质量"章节，包含所有评估维度
- 添加质量评分和说明，可视化质量分布（雷达图）
- 更新文档：质量评估指标说明

## Capabilities

### New Capabilities
- `code-quality/time-complexity`: 时间复杂度分析（静态分析循环嵌套、性能测试不同数据规模、复杂度评分与超时标注）
- `code-quality/space-complexity`: 空间复杂度分析（内存使用峰值监控、不必要内存分配识别、空间效率评分）
- `code-quality/readability`: 代码可读性评分（pylint/flake8/radon 集成、变量命名质量、注释覆盖率、函数长度和嵌套深度）
- `code-quality/style-consistency`: 代码风格一致性（black 格式检查、风格偏差统计、代码风格报告）

### Modified Capabilities
- `reporting/html-generator`: 需要扩展以支持代码质量章节和雷达图可视化

## Impact

**受影响模块**：
- `src/sandbox_executor.py` - 添加性能测试和内存监控
- `src/models.py` - 扩展结果模型以包含质量指标
- `src/reporting/html_generator.py` - 添加质量报告章节和可视化
- 新增模块：`src/code_quality/` - 质量分析核心逻辑
- `tests/` - 新增质量分析测试用例
- `requirements.txt` - 添加 pylint、flake8、radon、memory_profiler 依赖
- 文档更新：README.md、feature-roadmap.md

**边界**：
- 仅评估 Python 代码质量，不支持其他语言
- 复杂度分析基于启发式规则，不保证 100% 准确
- 不修改生成的代码，只评估和报告
