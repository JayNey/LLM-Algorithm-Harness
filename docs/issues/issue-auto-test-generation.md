# [创新功能] 自动生成测试用例

## 背景与目标

当前题目的测试用例由人工编写或从平台导入，覆盖率有限。自动生成测试用例功能可使用 LLM 根据题目描述生成边界测试用例，并通过模糊测试发现隐藏 bug，增强题目的测试覆盖率。

- 分类：测试工程
- 建议优先级：P3（低优先级，创新性强但实用性待验证）
- 相关文档：[feature-roadmap.md](../feature-roadmap.md#13-自动生成测试用例)

## 工作范围

### 1. 基于约束的测试生成
- 解析题目描述中的约束条件：
  - 输入范围（如 `1 <= n <= 10^5`）
  - 数据类型（整数、数组、字符串等）
  - 特殊限制（非负、有序、不重复等）
- 生成边界测试用例：
  - 最小值（如 `n = 1`）
  - 最大值（如 `n = 10^5`）
  - 空输入（如空数组 `[]`）
  - 单元素输入
  - 特殊值（如 0、负数、浮点边界）

### 2. LLM 辅助测试生成
- 使用 LLM 理解题目并生成测试用例：
  - Prompt 示例：
    ```
    根据题目描述，生成 5 个边界测试用例：
    题目：{problem.description}
    约束：{problem.constraints}
    输出格式：{"input": ..., "output": ...}
    ```
- 验证生成的测试用例格式正确

### 3. 模糊测试（Fuzzing）
- 随机生成大量测试输入：
  - 使用 Hypothesis 等模糊测试库
  - 根据题目约束生成随机数据
  - 执行代码并检测异常
- 记录导致失败的输入：
  - 崩溃（Crash）
  - 超时（Timeout）
  - 内存溢出
  - 断言失败

### 4. 覆盖率分析
- 使用 `coverage.py` 分析代码覆盖率
- 识别未覆盖的代码路径
- 生成覆盖率报告

## 验收标准

- [ ] 约束解析器正确提取题目约束
- [ ] 边界测试生成器生成至少 10 个有效测试用例
- [ ] LLM 生成的测试用例格式验证通过
- [ ] 模糊测试运行 1000 次迭代，记录失败用例
- [ ] 覆盖率分析集成到评估流程
- [ ] CLI 命令：`harness generate-tests --problem leetcode_1 --count 20`
- [ ] 文档更新：测试生成使用指南

## 边界

- 仅生成输入，不保证输出正确（需要参考实现验证）
- 模糊测试不保证找到所有 bug（概率性方法）
- 覆盖率分析仅统计，不强制要求 100% 覆盖

## 依赖与关联

- 前置：#6 [功能] 题目 Schema（已完成）
- 关联：代码质量评估（覆盖率作为质量指标）
- 后续扩展：基于反馈的自适应测试生成

## 技术要点

### 约束解析
```python
import re

def parse_constraints(description: str):
    constraints = {}
    # 提取数值范围
    match = re.search(r'(\d+)\s*<=\s*(\w+)\s*<=\s*(\d+)', description)
    if match:
        constraints[match.group(2)] = {
            'min': int(match.group(1)),
            'max': int(match.group(3))
        }
    return constraints
```

### 边界测试生成
```python
def generate_boundary_tests(constraints):
    tests = []
    for var, bounds in constraints.items():
        # 最小值
        tests.append({var: bounds['min']})
        # 最大值
        tests.append({var: bounds['max']})
        # 边界附近
        tests.append({var: bounds['min'] + 1})
        tests.append({var: bounds['max'] - 1})
    return tests
```

### 模糊测试
```python
from hypothesis import given, strategies as st

@given(st.lists(st.integers(), min_size=0, max_size=100))
def test_fuzzing(input_array):
    try:
        result = solution(input_array)
        assert isinstance(result, expected_type)
    except Exception as e:
        # 记录失败用例
        log_failure(input_array, str(e))
```

### 覆盖率分析
```python
import coverage

cov = coverage.Coverage()
cov.start()

# 执行代码
exec(code, globals())

cov.stop()
cov.save()

# 生成报告
cov.report()
```

## 预期收益

- 实现工作量：约 8-10 天
- 测试质量：提升测试覆盖率 20-30%
- 研究价值：自动化测试生成方法探索
- 实用性：**待验证**（生成的测试可能质量不稳定）

## 风险与挑战

1. **输出验证困难**：生成输入容易，但不知道正确输出
2. **LLM 不稳定**：生成的测试用例可能格式错误
3. **覆盖率提升有限**：随机测试难以覆盖复杂逻辑

## 建议

**延后实现**，理由：
- 创新性强但实用性不确定
- 需要参考实现来验证输出
- 优先实现确定性收益的功能
