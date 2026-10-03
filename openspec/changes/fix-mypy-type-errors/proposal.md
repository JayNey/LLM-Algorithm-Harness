## Why

CI 类型检查作业当前失败，在 40 个文件中有 494 个 mypy 类型错误。这些类型错误是技术债务，需要系统性解决以提高代码质量并更早地捕获潜在错误。

## What Changes

- 为所有缺少返回类型注解的函数添加类型注解（78 个 no-untyped-def 错误）
- 为所有缺少类型注解的变量添加类型注解（14 个 var-annotated 错误）
- 修复函数调用参数错误（192 个 call-arg 错误）
- 修复参数类型错误（65 个 arg-type 错误）
- 修复未定义属性错误（40 个 attr-defined 错误）
- 修复类型赋值问题（20 个 assignment 错误）
- 修复对未类型化函数的调用（27 个 no-untyped-call 错误）
- 确保所有文件通过 mypy 类型检查

## Capabilities

### New Capabilities
<!-- No new capabilities - this is a code quality improvement -->

### Modified Capabilities
<!-- No modified capabilities - type annotations do not change functional requirements -->

## Impact

- 40 个 Python 源文件将添加类型注解
- 高影响文件：`src/harness.py` (83 错误)、`src/sandbox_executor.py` (63 错误)、`src/main.py` (57 错误)、`src/ab_testing.py` (48 错误)、`src/llm_client.py` (44 错误)
- CI 类型检查作业将开始通过
- 无功能行为变更
- 代码可维护性和类型安全性提升
