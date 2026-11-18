# 隔离并行 ToT 执行状态

## Why
Issue #493：Harness task-service 为同一策略复用 runtime，ToT 将调用记录、响应、上下文和预算停止原因保存到实例字段，并行题目会互相重置、混入轨迹与 token。

## What Changes
- 为每次搜索建立独立状态，覆盖调用记录、响应、调用类型/深度和预算停止原因，并在退出时恢复上下文。
- 经真实 Harness task-service 共享 runtime 路径增加同步屏障回归，核对轨迹、token、异常和预算归属。
- 回归串行搜索、选中代码、隐藏判题和结果持久化。

## Capabilities
### New Capabilities
无。
### Modified Capabilities
- `strategies/tree-of-thoughts`：明确共享实例并行执行时各题调用记账和终止状态独立。

## Impact
实现集中于 src/strategies/tree_of_thoughts.py，测试集中于 ToT 与 Harness；不增加依赖，不改变公共结果结构和工厂共享策略。
