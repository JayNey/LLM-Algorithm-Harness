## Why

`POST /api/v1/tasks/{task_id}/pause` 已经能把运行中的实验、导入和基准任务标成 `paused`，但对应 worker 不会观察这个状态。它们会把剩余工作做完，再把任务写成 `completed` 或 `failed`，暂停因此不生效。

## What Changes

- 实验、导入和基准 worker 在下一个安全边界看到 `paused` 后停止继续派发新工作。
- 已经暂停的任务保持 `paused`，业务记录也停在 `paused`，不得再被写成 `completed` 或 `failed`。
- 不改暂停接口的入参，也不让这三类任务可以恢复。

## Capabilities

### New Capabilities

### Modified Capabilities

- `async-task-queue`: 运行中的实验、导入和基准任务被暂停后，worker 必须停在安全边界并保持暂停。

## Impact

- 代码：实验执行循环、导入处理循环、基准执行循环，以及三个 Celery worker。
- API：暂停接口的地址和请求不变。被暂停的实验、导入和基准不再在结束后变成完成或失败。
- 数据：不新增表或列。业务状态增加可观察到的 `paused`。
