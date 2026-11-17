# 变更提案

## Why

Self-Consistency 的候选和固定预算实验的重复组合可能使用同一个磁盘缓存键，导致一次模型响应被多次计入投票或实验结果。已在当前主分支通过真实磁盘缓存和模拟供应商复现，两条路径各产生三条结果，但均只调用一次供应商。详见 [issue #489](https://github.com/JayNey/LLM-Algorithm-Harness/issues/489)。

## What Changes

- Self-Consistency 的每个候选独立生成。`repeats > 1` 的实验在串行和并行模式下使用相同的独立采样规则。
- 记录采样身份、缓存命中状态和检查点恢复信息。常规缓存调用仍可回放相同请求，恢复操作仍可读取可信的已完成工作。
- 保留旧缓存和历史报告。曾启用缓存且可能重复回放的旧检查点需要重新运行才能产出可认证的独立样本。重新生成历史对比报告时注明采样身份无法验证。

## Capabilities

### New Capabilities

### Modified Capabilities

- `llm-response-cache`：定义独立采样和缓存回放的边界，以及 Self-Consistency 候选的观察与恢复语义。
- `experiment/budget-comparison`：定义重复组合的独立采样、恢复和历史报告口径。

## Impact

影响 LLM 客户端、Self-Consistency、实验运行和恢复，以及重新生成的对比报告。沿用现有生成参数、预算和计费接口。回归使用真实磁盘缓存和模拟供应商，可离线执行。
