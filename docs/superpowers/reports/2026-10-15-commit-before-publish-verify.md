# commit-before-publish 验证报告

结论：PASS

## 范围

- change：`commit-before-publish`
- 分支：`tweak/20261015/commit-before-publish`
- 验证模式：full。本次有 delta spec；`comet state scale` 统计 1 个任务、1 个 delta spec、19 个变更文件，结果也是 full。
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 升级判定

相对 `base_ref` 的路径数是 19，超过 tweak 文件数提示阈值。其中实现只改四个入口和两份测试：`api/services/experiment_service.py`、`api/services/benchmark_service.py`、`api/routes/files.py`、`api/routes/tasks.py`、`tests/test_async_task_submission.py`、`tests/test_api_monitoring_queue_compatibility.py`。没有新增表列，也没有新增接口。用户选择继续 tweak，不升级为完整 classic。

## 完整性

- tasks.md 1/1 已勾选。
- delta spec `async-task-queue` 修改 3 条既有需求、新增 1 条需求。新增的先落库和发布失败场景都有实现和测试。未改写的既有场景仍由原有测试覆盖。

| 场景 | 证据 |
| --- | --- |
| 实验入队先落库后发布 | `api/services/experiment_service.py` `start_experiment` 调用 `enqueue_task`；`tests/test_async_task_submission.py::test_experiment_start_commits_before_publish` 用第二条连接读到 `pending` |
| 实验入队发布失败 | `tests/test_async_task_submission.py::test_experiment_start_marks_failed_when_publish_raises` |
| 导入入队先落库后发布 | `api/routes/files.py` `import_uploaded` 调用 `enqueue_task`；`tests/test_async_task_submission.py::test_import_route_commits_before_publish` |
| 导入入队发布失败 | `tests/test_async_task_submission.py::test_import_route_marks_failed_when_publish_raises` |
| 基准入队先落库后发布 | `api/services/benchmark_service.py` `start_run` 调用 `enqueue_task`；`tests/test_async_task_submission.py::test_benchmark_start_commits_before_publish` |
| 基准入队发布失败 | `tests/test_async_task_submission.py::test_benchmark_start_marks_failed_when_publish_raises` |
| 通用任务创建先落库 | `api/routes/tasks.py` `create_task` 调用 `enqueue_task`；`tests/test_async_task_submission.py::test_generic_create_route_commits_before_publish` |
| 通用任务发布失败 | `tests/test_async_task_submission.py::test_generic_create_route_marks_failed_when_publish_raises` |

## 正确性

- 四个入口都在发布前提交任务记录，`send_task` 使用预生成的 `celery_task_id`。
- 发布失败时任务状态为 `failed`，错误信息为 `failed to publish task to broker`。
- 与 `design.md` 的三项决定一致：改调 `enqueue_task()`、这四个入口不使用 `on_before_publish`、发布失败沿用既有错误信息。
- `create_task()` 未改。`EvaluationService.resume_evaluation` 仍调用 `create_task()`。
- proposal 的目标已满足：四个入口先落库再发布；无数据库迁移。

## 一致性

- tweak 预设没有 Superpowers Design Doc（`design_doc` 为空）。设计依据是 `openspec/changes/commit-before-publish/design.md`，不存在与 `docs/superpowers/specs/` 的漂移。
- delta spec 与 `design.md` 无矛盾。

## 安全

- 通用创建和导入仍使用调用方的 `user_id`。
- 未新增密钥、凭据或日志输出。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/test_async_task_submission.py tests/test_tasks_api.py tests/test_api_monitoring_queue_compatibility.py tests/test_api_experiment_benchmark.py tests/test_api_files.py -q --no-cov` | 130 passed，退出码 0 |
| `python3 -m ruff check` 上述 6 个实现和测试文件 | All checks passed，退出码 0 |
| `python3 -m black --check` 上述 6 个文件 | 6 files would be left unchanged，退出码 0 |
| `comet classic openspec -- validate commit-before-publish --strict --type change` | Change is valid，退出码 0 |
