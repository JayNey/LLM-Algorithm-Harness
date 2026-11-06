## Why

#373 记录了调试会话把正常返回误报为执行失败的问题。#380 已改为读取真实结果的迭代列表，需要用回归测试锁定运行摘要及后续轨迹操作的行为。

## What Changes

- 验证正常返回的成功、答错和零轮结果均显示真实状态和轮次。
- 验证策略抛出的异常仍显示为执行失败，已完成运行的轨迹可以查询和导出。

## Capabilities

### New Capabilities

### Modified Capabilities

- `debugging/interactive-mode` — 明确运行摘要与策略异常的验收条件。

## Impact

涉及交互调试的 CLI 回归测试和现有 OpenSpec 规范。
