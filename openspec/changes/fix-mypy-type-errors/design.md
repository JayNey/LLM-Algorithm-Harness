# Design: Fix Mypy Type Errors

## Overview

系统性地解决代码库中的 494 个 mypy 类型错误，优先处理高影响文件和常见错误模式。采用分阶段方法，每个阶段聚焦特定错误类别。

## Implementation Approach

### Phase 1: High-Impact Files (Top 5)
优先修复包含最多错误的文件，这些文件占总错误数的 60%：

1. `src/harness.py` - 83 errors
2. `src/sandbox_executor.py` - 63 errors  
3. `src/main.py` - 57 errors
4. `src/ab_testing.py` - 48 errors
5. `src/llm_client.py` - 44 errors

### Phase 2: Missing Type Annotations (78 errors)
- 为所有缺少返回类型注解的函数添加 `-> ReturnType` 或 `-> None`
- 为所有缺少类型注解的变量添加类型提示
- 参考 PR #122 中已修复的文件作为示例

### Phase 3: Function Call and Argument Issues (257 errors)
- 修复 call-arg 错误 (192 errors)：缺少必需参数或多余参数
- 修复 arg-type 错误 (65 errors)：参数类型不匹配
- 确保函数调用与函数签名匹配

### Phase 4: Remaining Issues
- 修复 attr-defined 错误 (40 errors)：未定义的属性访问
- 修复 assignment 错误 (20 errors)：类型赋值不兼容
- 修复 no-untyped-call 错误 (27 errors)：调用未类型化函数

### Phase 5: Verification
- 在每个阶段后运行 `mypy src/ --ignore-missing-imports`
- 确保错误数量持续减少
- 最终验证：`mypy src/ --ignore-missing-imports` 返回 `Success: no issues found`

## Error Pattern Examples

### no-untyped-def
```python
# Before
def process_data(x):
    return x * 2

# After  
def process_data(x: int) -> int:
    return x * 2
```

### var-annotated
```python
# Before
lines = []

# After
lines: list[str] = []
```

### call-arg
```python
# Before
result = SandboxResult(success=True, output="test")

# After
result = SandboxResult(success=True, output="test", execution_time=0.0)
```

## Testing Strategy

- 在每个阶段后运行现有测试套件确保无功能回归
- 使用 mypy 增量检查验证类型错误减少
- 最终运行完整的 CI 流程确认类型检查通过

## Dependencies

- mypy (already installed)
- 无新增外部依赖

## Success Criteria

- 所有 494 个类型错误解决
- `mypy src/ --ignore-missing-imports` 返回成功
- CI 类型检查作业通过
- 所有现有测试继续通过
