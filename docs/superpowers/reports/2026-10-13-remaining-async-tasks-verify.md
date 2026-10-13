# remaining-async-tasks 验证报告

结论：PASS

## 范围

- change：`remaining-async-tasks`
- 分支：`tweak/20261013/remaining-async-tasks`
- 验证模式：full（10 个任务，1 个 delta spec，24 个变更文件）
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 完整性

- tasks.md 10/10 已勾选。
- delta spec `async-task-queue` 的 3 条需求都有实现：
  - 实验任务：`src/tasks/experiment.py`
  - 导入任务：`src/tasks/imports.py`
  - 基准任务：`src/tasks/benchmark.py`

## 正确性

| 场景 | 证据 |
| --- | --- |
| 提交后立即返回任务标识，且可查询为 pending | `tests/test_async_task_submission.py` |
| 成功执行实验 | `tests/test_experiment_task.py::test_run_experiment_task_success` |
| 实验失败留下错误 | `tests/test_experiment_task.py::test_run_experiment_task_failure_records_error` |
| 实验不属于该用户 | `tests/test_experiment_task.py::test_run_experiment_task_rejects_other_users_experiment` |
| 实验不是 pending | `tests/test_experiment_task.py::test_run_experiment_task_rejects_non_pending` |
| 实验执行关闭中断恢复 | `tests/test_experiment_task.py::test_execute_experiment_disables_recovery` |
| 导入进度 | `tests/test_import_task.py::test_run_import_task_reports_progress_and_completes` |
| 导入作业不存在时拒绝执行 | `tests/test_import_task.py::test_execute_import_missing_job_does_not_process` |
| 导入失败写入 result.detail | `tests/test_import_task.py::test_run_import_task_failure_records_result_detail` |
| 基准完成并保留准确率与成本 | `tests/test_benchmark_task.py::test_run_benchmark_task_completed_records_metrics` |
| 取消后的基准任务不再标成完成 | `tests/test_benchmark_task.py::test_run_benchmark_task_cancel_does_not_complete` |
| 基准运行不属于该用户 | `tests/test_benchmark_task.py::test_run_benchmark_task_rejects_other_users_run` |
| 基准运行不是 pending | `tests/test_benchmark_task.py::test_run_benchmark_task_rejects_non_pending` |
| 基准执行关闭中断恢复 | `tests/test_benchmark_task.py::test_execute_benchmark_disables_recovery` |

新鲜验证命令：

`python3 -m pytest tests/test_async_task_submission.py tests/test_experiment_task.py tests/test_import_task.py tests/test_benchmark_task.py tests/test_celery_app.py -q --no-cov`

结果：28 passed，退出码 0。

`python3 -m ruff check src/tasks src/celery_app.py tests/test_async_task_submission.py tests/test_experiment_task.py tests/test_import_task.py tests/test_benchmark_task.py`

结果：All checks passed，退出码 0。

`comet classic openspec -- validate remaining-async-tasks --strict --type change`

结果：Change is valid，退出码 0。

## 一致性

- proposal 的目标已满足：三个 Celery 任务可经现有 TaskManager 提交，状态写回 `async_tasks`，没有新 HTTP 端点，也没有数据库迁移。
- `design.md` 的四项决定都按原样实现：分模块、只用 `entity_id`、调用现有执行函数、路由到 `default` 队列。
- 本 tweak 没有 Superpowers Design Doc（`design_doc` 为空）。历史文档 `docs/superpowers/specs/2026-10-12-async-task-queue-design.md` 把实验表外键列为后续阶段设想；本次 `design.md` 与 delta spec 明确不采用该外键。二者之间没有未记录的实现偏差。

## 安全

- 导入任务先按 `user_id` 读取作业，不存在时抛出错误且不调用 `process_job`。
- 实验和基准任务都校验记录属于该用户；不属于该用户时任务失败且不执行。
- 没有新增密钥或凭据日志。
