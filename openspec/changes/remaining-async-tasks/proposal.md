## Why

Issue #149 要求把长时间运行的实验、题目导入和基准测试放进异步任务队列。评估任务已经由 Celery 的 `run_evaluation_task` 执行，剩下这三项仍走进程内线程或请求内后台任务，worker 重启后无法查询、取消或恢复。

## What Changes

- 新增 Celery 任务 `run_experiment_task`、`run_import_task`、`run_benchmark_task`，复用现有 TaskManager、状态和进度模型。
- 三个任务分别驱动已有的实验执行、上传导入和基准运行，并把状态写回对应记录与 `async_tasks`。
- 不新增 HTTP 端点，不修改现有实验、导入、基准接口的对外契约。
- 不新增数据库列；任务与业务记录通过现有 `AsyncTask.entity_id` 关联。

## Capabilities

### New Capabilities

- `async-task-queue`: 实验、题目导入和基准测试可以作为 Celery 任务创建、查询状态与进度，并在失败时留下错误信息。

### Modified Capabilities

## Impact

- 代码：`src/tasks/`、`src/celery_app.py`，以及实验、导入、基准的现有执行入口（只读调用，不改 API 契约）。
- API：继续使用已有的 `POST /api/v1/tasks` 及状态、取消、暂停、恢复端点。
- 依赖：沿用已配置的 Celery 与 Redis，不引入新组件。
