# 设计说明：websocket-progress

## 决策

1. **Redis Pub/Sub 作为跨进程通道**：celery worker 进程与 API 进程隔离，进度事件经 `progress:{task_id}` 频道广播；发布端 best-effort（连接失败仅记日志），保证 worker 在 Redis 故障时照常执行。
2. **发布点最小侵入**：只挂在 worker 既有节点（状态转 running 后、`on_unit_finished` 提交后、终态分支），不动执行语义。`problem.started`/`iteration.completed` 需要 TaskService/harness 新增回调，属执行引擎改动，列为非目标。
3. **WS 鉴权与所有权**：浏览器 WebSocket 无法自定义 header，token 走 query 参数；`AuthService.authenticate` 校验失败即断开（4401）。订阅时经 `TaskManager.get_task(task_id, user_id)` 做 owner 校验，非本人任务断开（4403）。
4. **断线回放 = 快照 + 后续事件**：订阅成功即发送 AsyncTask 当前快照（`task.snapshot`：status + progress + 计数），后续为实时事件。完整事件日志回放需要事件持久化，超出本 change。
5. **连接管理**：每连接维护 `channel -> asyncio.Task` 监听器；`unsubscribe`/断开时取消监听并退订 Redis 频道；`ping` 动作回 `pong`（保活）。Redis pubsub 监听器异常时向客户端发 `error` 事件并关闭连接，由客户端重连。
6. **可测试性**：`ProgressStream` 协议抽象订阅源（Redis 实现 + 测试用内存实现经 create_app 注入）；worker 侧 `publish_progress` 接受可选 redis 客户端参数便于断言。

## 非目标

- `problem.started` / `iteration.completed` 事件（需执行引擎回调扩展）
- 日志流推送（issue 标注可选）
- 完整事件日志持久化与任意点回放
- Socket.IO（用原生 FastAPI WebSocket 即可满足）
