## Why

多轮反馈策略（MultiRoundFeedbackStrategy）通过迭代改进代码，但缺少对代码质量演化的追踪分析。当前系统记录每轮迭代的执行结果，但无法回答：代码质量是否真的在提升？哪些迭代反而导致了质量下降？这使得难以理解迭代效果、识别过度优化或引入错误的关键节点。

## What Changes

- 新增代码演化分析模块，追踪多轮迭代中的质量指标变化
- 为每个迭代记录代码质量分数（复杂度、可读性、风格）
- 生成迭代趋势图表，可视化质量演化曲线
- 自动识别质量下降的迭代点，分析下降原因
- 在实验报告中集成演化分析章节

## Capabilities

### New Capabilities
- `analysis/code-evolution`: 追踪多轮迭代中代码质量的变化趋势，识别质量下降迭代并分析原因

### Modified Capabilities
<!-- 无现有 capability 的 requirement 变更 -->

## Impact

**新增文件：**
- `src/analysis/evolution.py` - 演化分析核心逻辑
- `src/analysis/metrics.py` - 代码质量指标计算（复杂度、可读性、风格）

**修改文件：**
- `src/strategies/multi_round_feedback.py` - 在每轮迭代后收集质量指标
- `src/models.py` - 扩展 IterationResult 以包含质量指标
- `src/report_generator.py` - 在报告中添加演化分析章节

**依赖：**
- 使用 `radon` 库计算代码复杂度（圈复杂度、认知复杂度）
- 使用 `pylint` 或 `flake8` 评估代码风格
- 使用 `matplotlib` 绘制趋势图表

**影响范围：**
- 仅影响使用 MultiRoundFeedbackStrategy 的实验
- 向后兼容：对不使用演化分析的场景无影响
- 报告生成逻辑扩展，但不改变现有报告结构
