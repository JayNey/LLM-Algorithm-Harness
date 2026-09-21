# [功能] 增强的错误分析

## 背景与目标

当前失败记录只保存错误类型和消息，缺少系统化的错误分析。增强的错误分析可自动分类错误类型、识别高频错误模式、提供修复建议，帮助快速定位模型弱点和改进方向。

- 分类：评估分析
- 建议优先级：P2（中等价值，提升调试效率）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#9-增强的错误分析)

## 工作范围

### 1. 错误自动分类
- 基于异常类型和消息的分类器：
  - **语法错误**：`SyntaxError`, `IndentationError`
  - **逻辑错误**：输出不匹配（无异常但测试失败）
  - **运行时错误**：`IndexError`, `KeyError`, `TypeError`, `AttributeError`
  - **超时错误**：执行时间超过限制
  - **内存溢出**：`MemoryError`，沙箱内存超限
  - **API 错误**：LLM 调用失败
  - **未知错误**：无法分类的异常

### 2. 错误模式识别
- 统计分析：
  - 各类错误的出现频率
  - 错误类型 × 难度分布
  - 错误类型 × 标签分布
- 高频错误模式提取：
  - 正则匹配常见错误（如 `list index out of range`）
  - 错误消息聚类（相似错误归为一类）
  - 生成错误趋势图（时间序列）

### 3. 修复建议生成
- 基于规则的修复提示：
  - `IndexError` → "检查数组边界，确保索引在有效范围内"
  - `KeyError` → "检查字典键是否存在，考虑使用 .get() 方法"
  - 超时 → "优化算法复杂度，避免不必要的循环"
- 可选：使用 LLM 生成修复建议
  - 输入：错误代码片段 + 错误消息
  - 输出：具体修复方案和参考代码

### 4. 报告增强
- 新增"错误分析"章节：
  - 错误分类饼图
  - 高频错误 Top 10 列表
  - 错误趋势折线图（跨实验对比）
  - 每个错误类型的修复建议

## 验收标准

- [ ] 错误分类器正确识别 7 种错误类型
- [ ] 错误模式识别覆盖 Top 10 高频错误
- [ ] 报告包含错误分析可视化图表
- [ ] 修复建议针对常见错误准确有效
- [ ] 单元测试覆盖所有错误类型
- [ ] 文档更新：错误分类规则说明

## 边界

- 仅分析 Python 代码错误，不支持其他语言
- 修复建议基于规则，不保证 100% 正确
- 不自动修复代码，只提供建议

## 依赖与关联

- 前置：#13 [修复] 完整保存失败结果（已完成）
- 关联：#15 [功能] 固定预算实验（错误分析纳入报告）
- 后续扩展：基于 LLM 的自动修复功能

## 技术要点

### 错误分类器
```python
def classify_error(error_type: str, error_msg: str) -> str:
    if error_type in ['SyntaxError', 'IndentationError']:
        return 'syntax_error'
    elif error_type in ['IndexError', 'KeyError', 'TypeError']:
        return 'runtime_error'
    elif 'timeout' in error_msg.lower():
        return 'timeout_error'
    elif error_type == 'AssertionError':
        return 'logic_error'
    # ...
```

### 错误模式提取
```python
from collections import Counter

# 统计高频错误消息
error_messages = [f.error_message for f in failures]
pattern_counter = Counter(error_messages)
top_patterns = pattern_counter.most_common(10)
```

### 修复建议映射
```python
FIX_SUGGESTIONS = {
    'IndexError': [
        "检查列表长度：使用 len(list) 确保索引有效",
        "避免硬编码索引：使用循环或列表推导式",
        "边界检查：if i < len(list): ..."
    ],
    'KeyError': [
        "使用 .get() 方法：dict.get(key, default)",
        "检查键是否存在：if key in dict: ...",
        "使用 defaultdict 避免缺失键错误"
    ]
}
```

## 预期收益

- 实现工作量：约 4-6 天
- 调试效率：快速定位问题类型，减少人工分析时间
- 用户价值：新手友好，提供具体改进方向
- 研究价值：系统化分析 LLM 的常见错误模式
