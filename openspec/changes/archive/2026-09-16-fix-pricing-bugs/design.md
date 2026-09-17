## Context

自定义模型定价功能已实现，但存在 6 个 bug 导致核心功能失效：成本累加错误、字段名不匹配、前缀匹配不可靠、类型标注错误和死代码。这些是实现级错误，不需要架构变更，只需针对性修复。

## Goals / Non-Goals

**Goals:**
- 修复 6 个已识别的正确性 bug
- 保持现有代码结构和 API 不变
- 确保所有现有测试通过

**Non-Goals:**
- 重构定价系统架构
- 添加新功能或优化性能
- 修改用户可见的行为（除了修复 bug 本身）

## Decisions

### Decision 1: 最小改动原则

**选择**: 只修复 bug，不改变周边代码结构

**理由**: 用户明确要求"改动尽量很小，不要改变已有功能"。这是 bug 修复，不是重构。

**替代方案**: 重构定价系统以避免类似 bug → 拒绝，超出当前 scope

### Decision 2: 修复 src/harness.py 中的成本计算

**Bug 1**: 期望 `trace['pricing_metadata']['total_cost']` 但该字段不存在
**Bug 2**: 从 `pricing_metadata` 读取 `prompt_tokens`/`completion_tokens`，但它们在 trace 顶层
**Bug 3**: 查找 `input_price_per_mtok`/`output_price_per_mtok`，但实际字段是 `prompt_price_per_1k`/`completion_price_per_1k`

**修复方案**:
- 在 LLMClient 设置 pricing_metadata 时计算并包含 `total_cost`
- 从 `trace` 顶层读取 token 计数，而非从嵌套字段
- 使用正确的字段名 `prompt_price_per_1k` 和 `completion_price_per_1k`

### Decision 3: 修复 src/utils/pricing.py 前缀匹配

**Bug 4**: 前缀匹配迭代 dict 键时未排序，可能匹配到错误的前缀（如 `gpt-4` 而非 `gpt-4o`）

**修复方案**: 在前缀匹配前按键长度降序排序，确保最长匹配优先

### Decision 4: 清理琐碎问题

**Bug 5**: `src/llm_client.py:237` 重复的 return 语句（死代码）
**Bug 6**: `src/utils/pricing.py:33` 使用小写 `any` 而非 `Any`

**修复方案**: 直接删除重复 return，导入并使用 `typing.Any`

## Risks / Trade-offs

**Risk**: 修改核心成本计算逻辑可能引入新 bug  
**Mitigation**: 运行现有测试验证，添加单元测试覆盖修复场景

**Risk**: 最长前缀匹配可能改变某些边缘情况的行为  
**Mitigation**: 这是 bug 修复，原行为本身就是错误的；测试会覆盖正确场景
