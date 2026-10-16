## Why

实验启动、题目导入、基准运行和通用 `POST /api/v1/tasks` 仍走 `create_task()`：先向 Celery 发布，再提交 `AsyncTask`。worker 可能在记录落库前取到消息，从而读不到任务。评估启动已经用 `enqueue_task()` 先落库再发布，这四个入口还没有对齐。

## What Changes

- 上述四个入口改为调用 `enqueue_task()`：预生成 `celery_task_id`，提交任务记录后再发布，发布使用同一标识。
- 发布失败时，已落库的任务标为 `failed`，并保存错误信息。
- 不改 `create_task()` 本身，也不改 `EvaluationService.resume_evaluation`。

## Capabilities

### New Capabilities

### Modified Capabilities

- `async-task-queue`: 实验、导入、基准的入队，以及通用任务创建，必须在发布队列消息之前落库。

## Impact

- 代码：`api/services/experiment_service.py`、`api/services/benchmark_service.py`、`api/routes/files.py`、`api/routes/tasks.py`，以及断言发布参数的测试。
- API：这四个入口的成功响应不变；发布失败时会留下 `failed` 任务，而不是不留记录。
- 数据：不新增表或列。
