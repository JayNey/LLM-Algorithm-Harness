## Why

`POST /api/v1/tasks/{task_id}/resume` 会读取 `AsyncTask` 上不存在的 `celery_task_name` 和 `celery_task_args`，调用即返回 500。评估任务已经能暂停并在 `TaskService` 留下检查点，但恢复接口接不回去。

## What Changes

- 修复恢复接口：对调用方自己的、状态为 `paused` 的评估任务，沿用同一条 `AsyncTask` 记录重新入队，并在发布 Celery 消息之前把状态落成 `pending`。
- 按 `task_type` 决定 Celery 任务名和参数，不新增数据库列。
- 非暂停任务、非评估任务，以及未知 `task_type`，返回 400，且不发布新的 Celery 消息、不改原记录。
- 补上真正调用恢复路径的测试。现有测试只把数据库状态改成 `running`，没有覆盖这个接口。

## Capabilities

### New Capabilities

### Modified Capabilities

- `async-task-queue`: 增加暂停评估任务的恢复行为。恢复必须回到同一任务标识，并在发布前落库。

## Impact

- 代码：`src/task_manager.py`、`api/routes/tasks.py`，以及对应测试。
- API：`POST /api/v1/tasks/{task_id}/resume` 从 500 变为可恢复评估任务；其他任务类型明确拒绝。
- 数据：不新增表或列。评估记录的 `async_task_id` 保持不变。
