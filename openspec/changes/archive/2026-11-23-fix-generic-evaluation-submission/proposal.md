# 修复通用入口的评估任务提交

## Why

Issue #512 指出：`POST /api/v1/tasks` 对评估草稿返回 201，却未建立 `Evaluation.async_task_id`，真实 worker 随后无法执行；不存在的实体也会生成占用额度的任务。评估专用启动入口已有完整提交机制，应复用以保持业务约束一致。

## What Changes

- 通用任务入口提交 evaluation 时复用已有评估启动业务服务，执行所有者、状态、凭据及并发额度校验，并在发布前原子保存任务和业务关联。
- 评估执行目标由已验证的 entity_id 决定；只接受省略或空执行参数、或仅包含同一 entity_id 的位置参数，拒绝其他位置参数和非空关键字参数。
- 保持成功响应为 201 和 AsyncTask 响应结构；拒绝他人、不存在、非 pending 和已入队实体，避免新增任务或消息。
- 增加真实路由、SQLite 及真实 worker 函数回归，模型执行使用本地替身，不调用付费模型。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `async-task-queue`：补充通用任务创建中评估业务关联、校验和实际可执行性的要求。

## Impact

预计影响通用任务路由、必要的评估启动复用点、相关测试及接口说明，共不超过 6 个交付文件；Comet/OpenSpec 流程产物另行保存。沿用当前干净的 main 工作区，采用 tweak 默认 direct/direct/off 配置。不修改数据库结构、任务类型白名单或其他业务的提交机制。

来源：https://github.com/JayNey/LLM-Algorithm-Harness/issues/512
