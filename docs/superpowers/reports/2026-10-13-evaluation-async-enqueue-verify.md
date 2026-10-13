# evaluation-async-enqueue 验证报告

结论：PASS

对应 issue #149 的 ②③ 收尾（评估启动接口接入 Celery + 修入队时序）。①（真实评估执行体，去 mock）已在入口决策中拆出，另开完整 change，不在本次范围。

## 范围

- change：`evaluation-async-enqueue`
- 分支：`comet/evaluation-async-enqueue`
- 验证模式：full（9 个任务，1 个 delta spec 能力，相对基线 18 个变更文件，其中含 Comet 元数据）
- 代码审查：跳过。`.comet.yaml` 的 `review_mode` 为 `off`，tweak 初始化时未启用自动审查。

## 完整性

- tasks.md 9/9 已勾选。
- delta spec `async-task-queue` 新增需求「评估可以作为异步任务执行」已实现：
  - 评估启动：`api/services/evaluation_service.py::start_evaluation` 经 `TaskManager.enqueue_task` 提交 `src.tasks.evaluation.run_evaluation_task`，评估保持 `pending`，返回聚合视图；不再用 `threading` + `_run_simulated` 进程内模拟。
  - 入队时序：`src/task_manager.py::enqueue_task` 预生成 `celery_task_id`，先 `commit`（含 `on_before_publish` 建立 `evaluation.async_task_id` 关联）再 `send_task(task_id=...)`，消除 worker 读不到关联的竞态。
  - 取消：`cancel_evaluation` 在有关联任务时经 `TaskManager.cancel_task` revoke Celery，再置评估 `cancelled`。
  - 重启恢复：`_recover_interrupted` 保留已入队（关联任务处于 pending/running/paused）的 `pending` 评估，与 #181 experiment/benchmark 行为一致。

## 正确性

| 场景 | 证据 |
| --- | --- |
| 成功提交评估任务：返回任务标识、评估保持 pending | `tests/test_api_auth.py::test_owner_evaluation_lifecycle`、`tests/test_api_database.py::test_enqueued_pending_survives_restart` |
| 入队先落库后发布：关联在发布前已提交、发布用预生成 id | `tests/test_task_manager.py::TestEnqueueTask::test_enqueue_commits_before_publish`、`test_enqueue_publishes_with_pregenerated_id` |
| 发布失败：任务置 failed 并抛出 | `tests/test_task_manager.py::TestEnqueueTask::test_enqueue_marks_failed_when_publish_raises` |
| 取消已入队评估：revoke Celery，评估与任务变 cancelled | `tests/test_api_database.py::test_cancel_revokes_celery_and_marks_cancelled` |
| 重启保留已入队 pending 评估 | `tests/test_api_database.py::test_enqueued_pending_survives_restart` |

新鲜验证命令与结果：

`python3 -m pytest tests/test_task_manager.py tests/test_api_database.py tests/test_api_auth.py tests/test_evaluation_service_async.py tests/test_celery_tasks.py tests/test_tasks_api.py tests/test_evaluation_async_flow.py tests/test_async_task_submission.py tests/test_celery_app.py -o addopts= -q`

结果：163 passed，退出码 0。

`python3 -m ruff check api/services/evaluation_service.py src/task_manager.py tests/test_task_manager.py tests/test_api_database.py tests/test_api_auth.py`

结果：All checks passed，退出码 0。

`python3 -m ruff format --check <同上 5 文件>`

结果：5 files already formatted，退出码 0。

`python3 -m mypy src/task_manager.py --ignore-missing-imports`

结果：Success: no issues found，退出码 0。

`comet classic openspec -- validate evaluation-async-enqueue --strict`

结果：Change is valid，退出码 0。

## 一致性

- proposal 目标已满足：评估启动接口只入队已有 `run_evaluation_task`，无新端点、无数据库结构变更、`create_task` 行为不变。
- design.md 决策 1–6 均按原样实现；决策 4 的措辞在本次验证中修正为与实现和 #181 一致（重启把所有 `running` 标失败、仅保留已入队 `pending`）。
- 本 tweak 没有 Superpowers Design Doc（`design_doc` 为空），检查项 3、7 不适用。
- delta spec 与 design.md 无矛盾。

## 验证阶段修复（verify_failures=1）

首轮完整验证发现两处非阻断问题，已回到 build 修复并重新验证通过：

- WARNING（一致性）：design.md 决策 4 原措辞暗示「running 且关联任务活跃」会被保留，但实现（正确地）与 #181 experiment/benchmark 一致，把所有 `running` 标失败。修正 design.md 措辞，未改实现。
- SUGGESTION（死代码）：移除模拟执行体后 `_TERMINAL_STATUSES` 在 `evaluation_service.py` 中已无引用，予以删除。

## 安全

- 启动/取消沿用现有 owner 校验（`_owned_task` + `auth.owned_key`）。
- 测试通过 mock `send_task`/`revoke`/`AsyncResult` 避免连接 Redis，无新增密钥或凭据日志。

## 遗留（非本 change 范围，基线既有）

- `tests/test_utf8_io.py` 仓库编码门禁失败：命中 `tests/test_async_task_integration.py` 三处 `read_text()` 未带 `encoding`。该文件由更早的独立提交（`32093db`，基线 main）引入，本 change 未触及；已用 `git stash` 证实在基线上同样失败。
- `tests/test_api_monitoring.py::test_download_closes_temporary_file_on_client_disconnect` 依赖 `pytest-asyncio`（pyproject 已声明但本机缺失），安装后通过；纯环境缺口。
