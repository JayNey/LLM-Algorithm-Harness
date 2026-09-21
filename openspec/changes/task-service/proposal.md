# 提议：提取可复用评测任务服务

## Problem

当前 Harness 在一次命令中串行执行所有题目，`max_workers` 没有生效，结果直到整批结束才保存。长任务无法查询、取消或恢复，Web/GUI 未来只能复制 CLI 的执行逻辑。

## Goal

- 用稳定的 `run_id` 和策略/题目/重复编号标识每个执行单元。
- 提供 queued、running、completed、failed、cancelled 生命周期和结构化事件。
- 逐单元原子持久化，支持配置/题库指纹校验后的恢复。
- 使用有界线程并发，取消时停止派发新单元，并把在途调用标记为 uncertain。
- 让现有 CLI 通过同一服务运行，同时为 Web/GUI 提供可复用的查询和事件数据。

## Non-goals

- 不引入 Redis、数据库、多用户认证或公网服务。
- 不承诺外部模型 API 恰好调用一次；在途请求只能记录为不确定。
- 不改变现有题目判题、策略和沙箱实现。

## Impact

新增 `src/task_service.py`，Harness 的 CLI 路径使用任务服务，结果目录增加 `tasks/<run_id>.json`；旧的直接 `AlgorithmHarness.run()` 调用保持兼容。
