## Why

每个 A/B 分层都从首变体开始分配，导致奇数层的余数集中到同一组。#364 复现了 20 个单题层全部进入首组，runner 仍生成报告的情况。

## What Changes

- 保持按难度与完整标签组合分层，将奇数层多出的一题交替分配给两个变体。
- 在执行前拒绝筛选后无法形成两个非空变体的题集，以及无法唯一归属的重复题目 ID。

## Capabilities

### New Capabilities

### Modified Capabilities

- `api/experiment-management` — 约束 A/B 分层的组间平衡与执行前校验。

## Impact

CLI 和 Celery worker 通过同一个 `ABTestRunner` 采用该规则。
