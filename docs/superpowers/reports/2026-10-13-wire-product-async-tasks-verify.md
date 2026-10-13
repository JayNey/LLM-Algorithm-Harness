# wire-product-async-tasks 验证报告

结论：PASS

本次是归档退回后的重新验证。实现与上次验证相同，证据按完整验证重新采集。

## 范围

- change：`wire-product-async-tasks`
- 分支：`tweak/20261013/wire-product-async-tasks`
- 验证模式：full（5 个任务，1 个 delta spec，相对基线 17 个变更文件）
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 完整性

- tasks.md 5/5 已勾选。
- delta spec `async-task-queue` 的三条修改需求都有实现：
  - 实验启动：`api/services/experiment_service.py` 提交 `src.tasks.experiment.run_experiment_task`，实验保持 `pending`，并返回 `task_id`
  - 题目导入：`api/routes/files.py` 提交 `src.tasks.imports.run_import_task`，返回 `job_id` 与 `task_id`，不再使用 `BackgroundTasks`
  - 基准启动：`api/services/benchmark_service.py` 创建 `pending` 运行并提交 `src.tasks.benchmark.run_benchmark_task`，返回 `task_id`
- API 重启会跳过已经挂有 pending 或 running 异步任务的 pending 实验和基准运行；没有任务的 pending 记录以及 running 记录仍标成中断。

## 正确性

| 场景 | 证据 |
| --- | --- |
| 实验运行立即返回任务标识且保持 pending | `tests/test_api_experiment_benchmark.py::test_full_lifecycle` |
| 实验失败后任务记录为 failed 并带错误 | `tests/test_experiment_task.py::test_run_experiment_task_failure_records_error` |
| 已入队的 pending 实验在 API 重启后仍为 pending，任务仍可查询 | `tests/test_api_experiment_benchmark.py::test_restart_keeps_queued_experiment_pending` |
| 没有任务的 pending 实验重启后仍标成中断 | `tests/test_api_experiment_benchmark.py::test_restart_marks_pending_experiment_failed` |
| 导入返回任务标识和作业标识，接口本身不跑完导入 | `tests/test_api_files.py::test_existing_upload_background_import_and_owner_progress` |
| 导入进度包含已处理数量、总数量和比例 | `tests/test_import_task.py::test_run_import_task_reports_progress_and_completes` |
| 导入作业不存在时拒绝执行 | `tests/test_import_task.py::test_execute_import_missing_job_does_not_process` |
| 基准运行立即返回任务标识且保持 pending | `tests/test_api_experiment_benchmark.py::test_run_results_and_learning_curve` |
| 基准完成后任务为 completed，运行记录含准确率与成本 | `tests/test_benchmark_task.py::test_run_benchmark_task_completed_records_metrics` |
| 取消后的基准任务不再标成 completed | `tests/test_benchmark_task.py::test_run_benchmark_task_cancel_does_not_complete` |
| 已入队的 pending 基准运行在 API 重启后仍为 pending，任务仍可查询 | `tests/test_api_experiment_benchmark.py::test_restart_keeps_queued_benchmark_pending` |

新鲜验证命令：

`python3 -m pytest tests/test_api_experiment_benchmark.py tests/test_api_files.py tests/test_api_database.py tests/test_experiment_task.py tests/test_import_task.py tests/test_benchmark_task.py tests/test_async_task_submission.py tests/test_celery_app.py -q --no-cov`

结果：121 passed，退出码 0。

`python3 -m ruff check api/services/experiment_service.py api/services/benchmark_service.py api/routes/files.py tests/test_api_experiment_benchmark.py tests/test_api_files.py`

结果：All checks passed，退出码 0。

`python3 -m black --check api/services/experiment_service.py api/services/benchmark_service.py api/routes/files.py tests/test_api_experiment_benchmark.py tests/test_api_files.py`

结果：5 files would be left unchanged，退出码 0。

`comet classic openspec -- validate wire-product-async-tasks --strict --type change`

结果：Change is valid，退出码 0。

## 一致性

- proposal 的目标已满足：三个产品启动接口只入队已有 Celery 任务并返回任务标识，没有新端点，也没有数据库迁移。
- `design.md` 的决定都按原样实现：启动接口只提交 `(id, user_id)`；重启保留已入队的 pending 记录；worker 仍使用 `recover=False`。
- 本 tweak 没有 Superpowers Design Doc（`design_doc` 为空）。历史文档里的实验表外键仍未采用，关联只走 `AsyncTask.entity_id`。

## 安全

- 启动接口沿用现有所有权校验：实验和基准按 owner 读取，导入使用当前登录用户。
- 测试通过 mock `send_task` 避免连接 Redis，没有新增密钥或凭据日志。
