## Why

实验、基准测试和题目导入的 Celery 任务已经能被 worker 执行，但对应的产品启动接口仍在 API 进程内用线程或 `BackgroundTasks` 运行。调用方从这些接口拿不到任务标识，进程重启后也无法再查询或取消。

## What Changes

- `POST /api/v1/experiments/{id}/run`、`POST /api/v1/benchmarks/suites/{id}/run` 和 `POST /api/v1/problems/import` 改为提交已有 Celery 任务，并在响应中返回任务标识。
- 提交后实验和基准记录保持 `pending`，由 worker 再改为 `running`。启动接口不再开后台线程或 `BackgroundTasks`。
- API 进程重启时，已经入队的 `pending` 实验和基准运行不再被标成失败。仍在 API 进程内处于 `running` 的旧记录继续标成中断。

## Capabilities

### New Capabilities

### Modified Capabilities

- `async-task-queue`: 产品启动接口成为实验、导入和基准任务的提交入口，并保留已入队记录越过 API 重启。

## Impact

- 代码：`api/services/experiment_service.py`、`api/services/benchmark_service.py`、`api/routes/files.py`，以及对应 API 测试。
- API：上述三个启动响应增加任务标识。不新增端点，不改数据库结构。
- 依赖：沿用现有 Celery 与 `TaskManager`。发布时仍需单独运行 worker。
