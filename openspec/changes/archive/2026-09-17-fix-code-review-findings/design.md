# Design: 修复代码审查发现的三个缺陷

## 修复方案

### 1. 保留原始错误信息（src/harness.py:163）

**当前实现：**
```python
if not hidden_result.all_passed:
    result.status = "failed"
    result.failure_category = (
        "system_error"
        if hidden_result.status != "failed"
        else "wrong_answer"
    )
    result.error_message = "Hidden evaluation failed"  # 无条件覆盖
```

**修复方案：**
- 只在原始error_message为空时才设置通用错误信息
- 如果公开测试已经产生了具体的错误信息，保留它以便调试

```python
if not hidden_result.all_passed:
    result.status = "failed"
    result.failure_category = (
        "system_error"
        if hidden_result.status != "failed"
        else "wrong_answer"
    )
    # 保留原始错误信息，仅在缺失时才填充通用信息
    if not result.error_message:
        result.error_message = "Hidden evaluation failed"
```

### 2. 移除冗余赋值（src/strategies/multi_round_feedback.py:134）

**当前实现：**
```python
if success:
    success = True  # 冗余赋值
    self.logger.info("solution_found", iteration=iteration)
    break
```

**修复方案：**
- 直接删除第134行的`success = True`语句
- 保留logger和break语句

```python
if success:
    self.logger.info("solution_found", iteration=iteration)
    break
```

### 3. 完善系统错误识别（src/strategies/multi_round_feedback.py:168）

**当前实现：**
```python
status = "success" if primary.all_passed and feedback.all_passed else "failed"
resource_statuses = {"timeout", "memory_error", "output_limit", "process_limit"}
for result in (primary, feedback):
    if result.status in resource_statuses:
        status = result.status
        break
```

**修复方案：**
- 在resource_statuses集合中添加`sandbox_error`和`backend_unavailable`
- 确保所有系统级错误都能被正确识别和保留

```python
status = "success" if primary.all_passed and feedback.all_passed else "failed"
resource_statuses = {
    "timeout", 
    "memory_error", 
    "output_limit", 
    "process_limit",
    "sandbox_error",
    "backend_unavailable"
}
for result in (primary, feedback):
    if result.status in resource_statuses:
        status = result.status
        break
```

## 影响范围

- **harness.py**: 1处修改（第163行条件判断）
- **multi_round_feedback.py**: 2处修改（删除第134行，修改第169行集合定义）
- 无接口变更
- 无数据库schema变更
- 无配置文件变更

## 测试策略

1. **错误信息保留测试**：验证公开测试失败且隐藏评估也失败时，原始错误信息被保留
2. **冗余代码移除测试**：确认移除赋值语句后逻辑正常
3. **系统错误分类测试**：验证sandbox_error和backend_unavailable被正确识别为系统错误而非wrong_answer
