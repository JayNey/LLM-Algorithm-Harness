# fix-task-resume 验证报告

结论：PASS

## 范围

- change：`fix-task-resume`
- 分支：`tweak/20261015/fix-task-resume`
- 验证模式：full（有 delta spec；`comet state scale` 亦判定为 full）
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 升级判定

相对 `main` 的路径数超过 tweak 文件数提示阈值。实现只改 `src/task_manager.py`、`api/routes/tasks.py` 和三份测试，没有新增表列，也没有新增接口。用户选择继续 tweak，不升级为完整 classic。

## 完整性

- tasks.md 2/2 已勾选。
- delta spec `async-task-queue` 新增 1 条需求、4 个场景，均有实现和测试。

| 场景 | 证据 |
| --- | --- |
| 恢复暂停的评估任务，沿用原标识，先落库再发布 | `src/task_manager.py` `resume_task` 在 `send_task` 之前 `commit`；`tests/test_task_manager.py::TestResumeTask::test_resume_paused_evaluation_requeues_same_task` |
| 拒绝非暂停任务，不发布、不改记录 | `tests/test_task_manager.py::TestResumeTask::test_resume_rejects_non_paused_without_publish`；路由侧 `tests/test_tasks_api.py::TestResumeTaskEndpoint::test_resume_running_task_fails` |
| 拒绝非评估任务，不发布、不改记录 | `tests/test_task_manager.py::TestResumeTask::test_resume_rejects_non_evaluation_without_publish`；`tests/test_tasks_api.py::TestResumeTaskEndpoint::test_resume_non_evaluation_does_not_publish` |
| 拒绝他人的任务，不发布 | `tests/test_task_manager.py::TestResumeTask::test_resume_rejects_other_users_task`；路由把含 “not found” 的 `ValueError` 转为 404（`api/routes/tasks.py` `call`） |

## 正确性

- `POST /api/v1/tasks/{task_id}/resume` 只调用 `TaskManager.resume_task`，不再读取不存在的 `celery_task_name` / `celery_task_args`。
- 成功路径返回同一条 `AsyncTask`，状态为 `pending`，关联评估的 `async_task_id` 不变且状态改为 `pending`。
- Celery 任务名为 `src.tasks.evaluation.run_evaluation_task`，参数为 `(entity_id,)`，`task_id` 使用提交前写入的新 `celery_task_id`。
- 发布失败时该任务标为 `failed` 并保留错误信息。这是 `design.md` 的决定，delta spec 未把发布失败列为成功场景。
- 与 `design.md` 的四项决定一致：同一条记录、只恢复评估、先落库再发布、逻辑放在 `TaskManager`。
- proposal 的目标已满足：暂停的评估任务可以恢复；其他类型明确拒绝；无数据库迁移。

## 一致性

- tweak 预设没有 Superpowers Design Doc（`design_doc` 为空）。设计依据是 `openspec/changes/fix-task-resume/design.md`，不存在与 `docs/superpowers/specs/` 的漂移。
- delta spec 与 `design.md` 无矛盾。

## 安全

- 恢复按 `user_id` 过滤，其他用户的任务不会被入队。
- 未新增密钥、凭据或日志输出。

## 命令证据

| 命令 | 结果 |
| --- | --- |
| `python3 -m pytest tests/test_task_manager.py tests/test_tasks_api.py tests/test_evaluation_async_flow.py -q --no-cov` | 69 passed，退出码 0 |
| `python3 -m ruff check src/task_manager.py api/routes/tasks.py tests/test_task_manager.py tests/test_tasks_api.py tests/test_evaluation_async_flow.py` | All checks passed，退出码 0 |
| `python3 -m black --check` 上述 5 个文件 | 5 files would be left unchanged，退出码 0 |
| `comet classic openspec -- validate fix-task-resume --strict --type change` | Change is valid，退出码 0 |
