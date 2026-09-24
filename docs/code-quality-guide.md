# 代码质量评估使用指南

本文档说明如何使用 LLM Algorithm Harness 的代码质量评估功能。

## 概述

代码质量评估功能提供了超越正确性的全面代码评价，包括四个维度：

1. **时间复杂度分析** - 静态分析和性能测试
2. **空间复杂度分析** - 内存使用监控
3. **代码可读性评分** - 多工具集成分析
4. **代码风格一致性** - 格式规范检查

## 快速开始

### 基本使用

```python
from src.code_quality.analyzer import CodeQualityAnalyzer

# 创建分析器（所有维度启用）
analyzer = CodeQualityAnalyzer()

# 分析代码
code = """
def solution(nums, target):
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            if nums[i] + nums[j] == target:
                return [i, j]
    return []
"""

metrics = analyzer.analyze(code)

# 查看结果
print(f"Overall Score: {metrics.overall_score}/100")
print(f"Time Complexity: {metrics.time_complexity.static_analysis}")
print(f"Loop Nesting: {metrics.time_complexity.loop_nesting_depth}")
```

### 选择性启用维度

```python
# 只启用部分维度
analyzer = CodeQualityAnalyzer(
    enable_time_analysis=True,
    enable_space_analysis=False,
    enable_readability_analysis=True,
    enable_style_analysis=False
)
```

## 在 Harness 中使用

### 配置质量分析

在 `HarnessConfig` 中添加质量分析器：

```python
from src.harness import AlgorithmHarness
from src.code_quality.analyzer import CodeQualityAnalyzer

# 创建 harness
harness = AlgorithmHarness(config)

# 启用质量分析
harness.quality_analyzer = CodeQualityAnalyzer()

# 运行评估
reports = harness.run()
```

### 访问质量指标

执行结果中包含质量指标：

```python
for result in results:
    if result.quality_metrics:
        print(f"Problem: {result.problem_id}")
        print(f"Quality Score: {result.quality_metrics['overall_score']}")
```

## 各维度详解

### 1. 时间复杂度分析

**输出字段：**
- `static_analysis`: Big-O 复杂度推断（如 "O(n^2)"）
- `loop_nesting_depth`: 最大循环嵌套深度
- `performance_score`: 性能评分（0-100）
- `execution_times`: 不同规模的执行时间

**示例：**
```python
time_comp = metrics.time_complexity
print(f"Complexity: {time_comp.static_analysis}")
print(f"Performance Score: {time_comp.performance_score}/100")
```

### 2. 空间复杂度分析

**输出字段：**
- `peak_memory_mb`: 峰值内存使用（MB）
- `memory_efficiency_score`: 空间效率评分（0-100）

### 3. 可读性分析

**输出字段：**
- `pylint_score`: Pylint 评分（0-10）
- `flake8_issues`: Flake8 发现的问题数
- `cyclomatic_complexity`: 平均圈复杂度
- `readability_score`: 综合可读性评分（0-100）

### 4. 风格一致性

**输出字段：**
- `black_compliant`: 是否符合 Black 格式
- `style_violations`: 风格违规数量
- `style_score`: 风格评分（0-100）

## 依赖要求

确保安装了以下工具：

```bash
pip install pylint>=3.0.0 flake8>=6.0.0 radon>=6.0.0 black>=23.0.0
```

## 性能考虑

- 质量分析会增加总体运行时间（约 10-30%）
- 可以选择性启用需要的维度以提高性能
- 静态分析工具（pylint/flake8/radon）需要额外时间

## 错误处理

质量分析失败不会阻塞正确性测试：

```python
if metrics.analysis_errors:
    print("Analysis errors:", metrics.analysis_errors)
```

各维度独立运行，某个维度失败不影响其他维度。

## 报告集成

质量指标会自动包含在 HTML 报告中，包括：
- 质量评分卡片
- 雷达图可视化
- 详细指标表格

## 常见问题

**Q: 分析器找不到 pylint/flake8/radon？**

A: 确保这些工具已安装并在 PATH 中。如果工具不可用，对应维度会返回 None，不会报错。

**Q: 性能测试需要多长时间？**

A: 取决于代码复杂度和测试用例大小，通常每个问题增加 5-15 秒。

**Q: 可以自定义评分权重吗？**

A: 可以修改 `CodeQualityMetrics.calculate_overall_score()` 方法中的权重。

## 示例输出

```json
{
  "overall_score": 75.5,
  "time_complexity": {
    "static_analysis": "O(n^2)",
    "loop_nesting_depth": 2,
    "performance_score": 70.0
  },
  "readability": {
    "pylint_score": 8.5,
    "flake8_issues": 2,
    "readability_score": 80.0
  }
}
```
