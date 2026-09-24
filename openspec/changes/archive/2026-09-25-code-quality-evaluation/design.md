## 架构概览

新增 `src/code_quality/` 模块，包含四个分析器，每个对应一个质量维度。沙箱执行器扩展以支持性能测试和内存监控。报告生成器扩展以包含质量章节和可视化。

```
src/code_quality/
├── __init__.py
├── time_analyzer.py      # 时间复杂度分析
├── space_analyzer.py     # 空间复杂度分析
├── readability_analyzer.py  # 可读性评分
└── style_analyzer.py     # 风格一致性检查
```

## 核心组件

### 1. 时间复杂度分析器 (time_analyzer.py)

**输入**：代码字符串、问题定义
**输出**：时间复杂度评分对象

- 静态分析：使用 AST 识别循环嵌套层数
- 性能测试：生成 10x、100x、1000x 规模测试数据，测量执行时间
- 复杂度推断：根据时间增长率推断实际复杂度
- 超时标注：标记超过阈值的执行

### 2. 空间复杂度分析器 (space_analyzer.py)

**输入**：代码字符串、问题定义
**输出**：空间复杂度评分对象

- 使用 `tracemalloc` 监控内存使用峰值
- 识别不必要的内存分配模式（重复创建大对象）
- 计算空间效率评分：实际内存 / 理论最优内存

### 3. 可读性分析器 (readability_analyzer.py)

**输入**：代码字符串
**输出**：可读性评分对象

集成静态分析工具：
- `pylint`：综合质量评分（0-10）
- `flake8`：风格问题计数
- `radon`：圈复杂度（McCabe）

评估维度：
- 变量命名质量
- 注释覆盖率
- 函数长度和嵌套深度

### 4. 风格一致性分析器 (style_analyzer.py)

**输入**：代码字符串
**输出**：风格一致性评分对象

- 使用 `black --check` 检查格式
- 统计风格偏差数量
- 生成代码风格报告

## 沙箱执行器扩展

**修改**：`src/sandbox_executor.py`

添加新方法：
- `execute_with_performance_profiling()` - 性能测试
- `execute_with_memory_profiling()` - 内存监控

这些方法在现有沙箱执行的基础上添加监控层，不影响现有正确性测试。

## 数据模型扩展

**修改**：`src/models.py`

添加新数据类：
```python
@dataclass
class CodeQualityMetrics:
    time_complexity: TimeComplexityScore
    space_complexity: SpaceComplexityScore
    readability: ReadabilityScore
    style_consistency: StyleConsistencyScore

@dataclass
class TimeComplexityScore:
    static_analysis: str  # "O(n)", "O(n^2)", etc.
    measured_growth_rate: float
    is_timeout: bool
    execution_times: Dict[str, float]  # {scale: time}

# 类似地定义其他评分类
```

在 `AlgorithmResult` 中添加 `quality_metrics: Optional[CodeQualityMetrics]` 字段。

## 报告生成器扩展

**修改**：`src/reporting/html_generator.py`

添加新函数：
- `generate_quality_section()` - 生成质量章节 HTML
- `generate_quality_radar_chart()` - 生成雷达图 SVG

质量章节包含：
- 四个维度的评分卡片
- 雷达图可视化（使用 Chart.js 或内联 SVG）
- 详细的质量指标表格

## 工作流集成

在 `src/harness.py` 中：
1. 代码生成后，调用 `CodeQualityAnalyzer.analyze(code, problem)`
2. 将质量指标附加到 `AlgorithmResult`
3. 报告生成时包含质量章节

质量分析是可选的（可通过配置开关控制），不影响现有正确性测试流程。

## 依赖管理

新增依赖（添加到 requirements.txt）：
- pylint>=3.0.0
- flake8>=6.0.0
- radon>=6.0.0
- memory_profiler>=0.61.0

## 错误处理

质量分析失败不应阻塞整体评估：
- 每个分析器独立运行，带 try-except
- 分析失败时返回 None，报告中标记为"分析失败"
- 记录错误日志但继续执行

## 性能考虑

- 性能测试可能增加总体运行时间（3-5 倍）
- 建议作为可选功能，默认关闭或仅在最终评估时启用
- 提供配置选项控制测试规模和超时阈值
