## Context

评估任务已经通过 `run_evaluation_task` 进入 Celery。实验、题目导入和基准运行各自仍在 API 进程里用线程或 `BackgroundTasks` 执行。见 `proposal.md` 的 Why。任务队列的创建、查询、取消和暂停接口已经存在，`AsyncTask.entity_id` 可以指向业务记录。

## Goals / Non-Goals

**Goals:**

- 提供三个可被现有 TaskManager 提交的 Celery 任务，覆盖实验、导入和基准运行。
- 任务状态、进度和错误信息写回 `async_tasks`，并同步到已有的实验、导入作业或基准运行记录。
- 执行逻辑调用现有服务，不重写实验、导入或基准算法。

**Non-Goals:**

- 不替换 `start_experiment`、基准 `start_run` 和 `/problems/import` 现有的进程内后台执行。
- 不新增 HTTP 端点，不加 `async_task_id` 外键，不引入 Flower。
- 不改变评估任务的行为。

## Decisions

1. 每个任务一个模块：`src/tasks/experiment.py`、`src/tasks/imports.py`、`src/tasks/benchmark.py`。任务名分别为 `src.tasks.experiment.run_experiment_task`、`src.tasks.imports.run_import_task`、`src.tasks.benchmark.run_benchmark_task`。备选是把三个函数放进一个文件；分开后与现有 `evaluation.py` 一致，失败时也更容易定位。
2. 关联只用 `AsyncTask.entity_id`：实验 id、导入 job id、基准 run id。备选是给三张业务表加 `async_task_id`；现有任务表已经保存这种关联，避免再做迁移。
3. 任务函数接收业务 id 和 `user_id`。它先确认记录属于该用户且处于可执行状态，再调用现有执行函数，最后按结果更新 `AsyncTask` 与业务记录。进度沿用评估任务的 `current` / `total` / `message` 结构。
4. Celery 路由把这三个任务放到已有的 `default` 队列。评估任务继续走 `evaluations` 队列，避免长实验占满评估 worker 的唯一变化是队列隔离已经存在，这里不新开队列。

## Risks / Trade-offs

- [现有 HTTP 启动路径仍用线程] → 本变更只保证经任务 API 提交的工作进入 Celery；两条路径并存，直到后续单独切换。
- [导入作业的进度存在文件服务而不是 `AsyncTask.progress`] → 任务在批次更新时同步写入 `AsyncTask.progress`，查询任务接口即可看到进度。
- [worker 里重建服务需要数据库和认证配置] → 与 `run_evaluation_task` 一样在任务内创建会话；缺配置时把任务标为 `failed` 并写入错误信息。

## 继续 tweak 的确认

用户已确认继续 tweak，不升级为完整 classic。触发提示的是改动会超过 6 个文件，并且任务会调用实验、导入和基准三个现有模块。确认原因：按本精简方案直接实现这三项 Celery 任务，不改数据库、不改现有 HTTP 契约。

## Migration Plan

无数据迁移。部署时重启 Celery worker，使新任务名可被发现。回滚时移除这三个任务模块并重启 worker；已经写入的 `async_tasks` 行仍可由现有清理任务删除。
