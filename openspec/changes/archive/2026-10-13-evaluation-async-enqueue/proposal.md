## Why

评估任务的 Celery 实现 `run_evaluation_task` 已存在，但产品启动接口 `POST /api/v1/evaluations/{id}/start` 仍在 API 进程内用线程跑模拟执行（`_run_simulated`），既不调用 worker，也在进程重启后丢失。#181 已把实验、导入、基准接入队列，评估是最后一个仍走进程内线程的启动路径。

## What Changes

- `POST /api/v1/evaluations/{id}/start` 改为提交已有的 `run_evaluation_task`；提交后评估记录保持 `pending`，由 worker 改为 `running`。移除进程内线程与 `_run_simulated` 模拟执行。
- 入队时序修正：AsyncTask 记录及其与 `evaluation.async_task_id` 的关联在提交 Celery 消息之前先落库，worker 可靠解析到关联任务；预生成 `celery_task_id` 并以该 id 发布，不改数据库结构。
- `POST /api/v1/evaluations/{id}/cancel` 在存在关联任务时通过 `TaskManager` revoke Celery 任务，再把评估置为 `cancelled`。
- API 进程重启不再把已入队的 `pending` 评估标成失败；没有关联任务的 `pending` 评估与 `running` 评估仍标成中断。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `async-task-queue`: 新增“评估可以作为异步任务执行”需求——评估启动接口成为 `run_evaluation_task` 的提交入口，入队先落库后发布，并保留已入队记录越过 API 重启。

## Impact

- 代码：`src/task_manager.py`（新增先落库后发布的入队方法）、`api/services/evaluation_service.py`（start/cancel/恢复逻辑，移除模拟执行），以及对应 API/服务测试。
- API：`start`/`cancel` 仍返回评估视图，不新增端点，不改数据库结构。
- 依赖：沿用现有 Celery 与 `TaskManager`；发布时需单独运行 worker。真实评估执行体（去 mock）不在本次范围，另开 change。
