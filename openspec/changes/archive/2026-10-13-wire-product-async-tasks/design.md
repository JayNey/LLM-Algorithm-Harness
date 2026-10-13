## Context

评估创建已经通过 `TaskManager.create_task` 提交 `run_evaluation_task`。实验、导入和基准的 Celery 任务在 `src/tasks/` 中，要求业务记录处于 `pending` 后再由 worker 执行。产品启动接口目前把实验和基准标成 `running` 并开线程，导入则使用 `BackgroundTasks`。

## Goals / Non-Goals

**Goals:**

- 三个启动接口提交对应的已有 Celery 任务并返回任务标识。
- 提交后实验和基准保持 `pending`。
- 已入队的 `pending` 记录在 API 重启后仍然可被 worker 执行。

**Non-Goals:**

- 不新增任务类型，不改 Celery 任务内部的执行、进度或取消逻辑。
- 不把暂停/恢复扩到这三类任务。
- 不引入 Flower，不加数据库列。

## Decisions

1. 启动接口只入队。实验运行接口在记录仍为 `pending` 时调用 `TaskManager.create_task`，任务名为 `src.tasks.experiment.run_experiment_task`，参数为实验 id 和用户 id。基准运行接口创建 `pending` 运行后同样提交 `src.tasks.benchmark.run_benchmark_task`。导入接口创建作业后提交 `src.tasks.imports.run_import_task`，不再调用 `BackgroundTasks`。
2. 响应在现有字段上增加 `task_id`。实验和基准仍返回原来的资源视图，导入仍返回 `job_id`。
3. 重启恢复只把没有对应 `AsyncTask` 的 `pending` 记录，以及所有 `running` 记录，标成失败。已经入队的 `pending` 记录保留。worker 侧继续使用 `recover=False`。

## 继续 tweak 的确认

用户已确认继续 tweak，不升级为完整 classic。触发提示的是改动会跨实验、基准和导入三个模块，并且文件数会超过 6 个。确认原因：只把三个已有启动接口改成提交已有 Celery 任务，不新增任务类型，不改数据库。

## Risks / Trade-offs

- [测试现在等待进程内线程跑完] → 启动接口测试改为断言任务标识和 `pending`；仍需验证执行结果的用例直接调用服务的执行函数，并 mock Celery `send_task`，避免依赖 Redis。
- [没有 worker 时任务停在 pending] → 与评估任务相同，部署时要启动已有 worker。
