# Proposal

## Why

默认判题先把整数转换为浮点数，再套用相对容差。因此应为 `1000000` 的结果 `1000001` 可能通过公开和隐藏测试，影响评测通过率。[Issue #488](https://github.com/JayNey/LLM-Algorithm-Harness/issues/488)

## What Changes

- 整数逐值精确比较，嵌套结果遵循同一规则。布尔值仅匹配相同布尔值，交换实际值与期望值仍得到相同结果。
- 保留现有浮点容差、无序列表匹配和节点适配逻辑。
- 标记判题契约版本，阻止增量评估复用旧契约结果，并说明如何重评受影响的历史评分。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `execution-protocol` 补充默认容差判题的数值类型边界。
- `incremental-evaluation` 将判题契约版本纳入题目指纹。

## Impact

影响共享判题逻辑和 CLI 增量评估。既有历史报告保留原评分，需要新建评估获取新版评分。
