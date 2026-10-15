## Why

Issue #150 要求为评估任务提供 WebSocket 实时进度推送。#149/#181 已交付 Celery 队列（AsyncTask 表 + `TaskManager.update_task_progress` + `src/tasks/evaluation.py` worker），但 worker 与前端之间没有推送通道，前端只能轮询。

## What Changes

- 事件发布：worker（`src/tasks/evaluation.py`）在 started/单元完成/终态等节点向 Redis 频道 `progress:{task_id}` 发布事件（尽力而为，Redis 不可用时静默降级，绝不影响任务执行）。
- WebSocket 端点 `/api/v1/ws/progress`：token 鉴权（query 参数）、`subscribe/unsubscribe/ping` 协议、按任务频道转发 Redis 事件、订阅即回放当前任务快照（断线重连后先拿到最新状态）。
- 事件类型：`task.started` / `task.progress` / `problem.completed` / `task.completed` / `task.failed` / `task.paused` / `task.cancelled`（`problem.started`/`iteration.completed` 需要执行引擎新增回调，列入非目标；日志流为 issue 标注的可选项，列入非目标）。
- 频道抽象 `ProgressStream`（Redis 实现默认；测试可注入内存实现），多 worker 经 Redis Pub/Sub 自然路由。

## Capabilities

### New Capabilities
- `api/progress-streaming`: 评估任务的实时进度事件发布与 WebSocket 订阅通道。

### Modified Capabilities
无。

## Impact

影响 `api/`（新增 ws 路由与进度模块）、`src/tasks/evaluation.py`（数处发布调用）与文档。不改变任务执行语义；Redis 故障时功能降级但任务不受影响。
