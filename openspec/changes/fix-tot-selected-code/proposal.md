## Why

Issue #347：ToT 已测试最高分叶子，却从最后扩展的父节点保存代码，一层树会返回空代码并跳过隐藏评测。

## What Changes

- 最终结果显式保存选中且执行的叶子代码，不再依赖探索历史的最后一项。
- 无有效代码时返回提取失败，保留公开执行失败时的所选代码和失败结果。
- 用确定性回归覆盖深度、遍历顺序、剪枝及真实 Harness 隐藏评测入口。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `strategies/tree-of-thoughts`：明确结果代码、公开执行和隐藏执行使用同一所选叶子；无代码时明确失败。

## Impact

仅修改 ToT 策略及其测试；不修改共享结果工厂、Harness、模型调用计费或公开 API。
