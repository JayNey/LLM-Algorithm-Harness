# 实验取消状态同步验证报告

结论：PASS。2/2 任务完成，1 项 delta requirement 的 12 个场景均有实现和回归证据，设计与规格一致。change `experiment-cancellation-sync`，关联 Issue #295，分支 `comet/experiment-cancellation-sync`，基线 `831e5fe624ecf54d36f4c88c952615725a97e380`。

## 最终行为与设计一致性

- 取消、暂停、启动和终态通过相同任务锁顺序更新 AsyncTask 与所属 Experiment，状态、首次开始与结束时间一致。
- SQLite 使用无值变化 UPDATE 获取写锁；PostgreSQL 锁定同一任务行，按 task → experiment 顺序写入。模型执行不持有这些锁。
- Worker 启动、正常返回、异常、进度与 Celery 状态回填不会覆盖已取消状态。取消后删除实验，晚到 Worker 仍返回 cancelled，不重建业务记录或把任务写成 failed。
- 取消时既检查 AsyncTask 终态，也保护业务已结束但旧 Worker 任务回调尚未完成的窗口。
- 服务收尾使用 owner/status 条件 UPDATE，同一事务保存产物路径、业务终态和任务终态。取消在前时不写入结果；完成在前时拒绝取消。
- 组合边界停止回调识别 paused 和 cancelled。已开始组合可以做完，后续组合不再派发。
- 仅三处生产文件和两处测试文件；无 schema、依赖或公开端点变更。用户 A2 已确认继续 tweak 并使用新分支；按 tweak 省略完整 Superpowers Design Doc 与 plan。

## 规格场景映射

| 场景 | 验证证据 |
| --- | --- |
| 成功提交实验任务 | 既有 TestExperiments.test_full_lifecycle、异步提交测试 |
| 实验入队先落库后发布 | 既有 test_async_task_submission.py 与 TaskManager 入队测试 |
| 实验入队发布失败 | 既有 TaskManager 发布失败回归；同步逻辑扩展到 Experiment |
| 查询实验进度 | test_execute_records_percentage_and_current_step |
| 暂停正在执行的实验 | test_run_experiment_task_keeps_paused_status、test_execute_marks_experiment_paused_from_other_connection |
| 实验失败留下错误 | test_run_experiment_task_failure_records_error、TestExperiments.test_runner_failure_marks_experiment_failed |
| 重启保留已入队实验 | TestExperiments.test_restart_keeps_queued_experiment_pending |
| 重启保留执行中实验 | test_api_restart_worker_recovery.py |
| 取消后刷新与删除 | test_cancel_synchronizes_experiment_and_allows_delete（pending/running/paused）、TestExperiments.test_cancel_refresh_and_delete（running/paused） |
| 取消先于晚到写入 | test_stale_task_writer_cannot_override_cancellation、test_celery_result_read_racing_cancel_preserves_cancelled、test_cancelled_delivery_does_not_start_or_fail、test_worker_late_return_or_exception_preserves_cancelled、test_service_late_runner_outcome_preserves_cancelled |
| 完成先于取消 | test_stale_cancel_rejects_already_finished_task、test_cancel_respects_business_terminal_before_task_callback、test_concurrent_cancel_and_completion_commit_consistent_pair |
| 取消所有权隔离 | test_cancel_cannot_touch_another_owners_records、TestExperiments.test_other_user_cannot_cancel_experiment_task |

## 验证证据

- RED：新增取消回归在修复前 22 failed / 1 passed；额外业务终态保护回归修复前 2 failed。失败均落在预期状态不一致或终态被覆盖断言。
- GREEN：`python3 -m pytest tests/test_experiment_cancellation.py tests/test_experiment_task.py tests/test_task_manager.py -q --no-cov`，73 passed。
- HTTP/API：`python3 -m pytest tests/test_api_experiment_benchmark.py -q --no-cov`，37 passed。
- 并发：真实文件 SQLite、独立连接与两个线程，在首个事务写业务记录前阻塞，让竞争操作到达；验证取消获胜与完成获胜两条顺序，无 sleep 时序猜测。
- `ruff check .`、`black --check .`（352 files）、`python3 scripts/find_missing_encoding.py`（0）、`git diff --check`：通过。
- `python3 -m mypy src/task_manager.py src/tasks/experiment.py api/services/experiment_service.py --follow-imports=silent --ignore-missing-imports`：3 files 通过。
- `python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/issue-295-wheels`：通过，生成 llm_algorithm_harness-0.1.0-py3-none-any.whl。
- `comet classic openspec -- validate experiment-cancellation-sync --strict`：通过。
- 完整离线测试：`python3 -m pytest -m "not online"`，3392 passed / 11 skipped / 14 errors；14 个错误均为 `tests/test_deployment_readiness.py` 的共享夹具在绑定 127.0.0.1 临时端口时被沙箱拒绝（PermissionError），没有测试断言失败。允许该夹具所需的本机服务权限后补跑 `python3 -m pytest tests/test_deployment_readiness.py -q --no-cov`，14 passed。两次合计 3406 项通过，11 项跳过，未将分次结果描述为单次全绿。
- 覆盖率：完整测试运行产出的总覆盖率 92.72%；独立检查 `coverage report --include="src/*" --fail-under=90` 为 91.40%，`coverage report --include="api/*" --fail-under=81` 为 94.90%，均通过。
- 全量错误用例：test_nginx_runtime_pid_is_isolated；test_unready_blocks_business_and_recovers 的 evaluations/auth-login/ws-progress 三种路径；test_probe_error_and_timeout_fail_closed 的 401/403/500/timeout；test_probe_is_get_without_client_credentials_body_or_query；test_business_errors_are_preserved 的 401/403/500；test_probe_requests_do_not_hit_business_rate_limit；test_websocket_upgrade_headers_survive_admission。上述 14 项均已补跑通过。
- Comet CLI 0.4.0 的 preset resolver 在 build 仅接受 verify_mode=light，因此提前执行 scale/set full 会报告配置不完整；保留初始化的 light，通过 build guard 后再在 verify 阶段设置 full，遵循同一公开 CLI 和原 workflow，不修改 Runtime 或伪造状态。

## 最终验证阶段

- 最终定向复测：`python3 -m pytest tests/test_experiment_cancellation.py tests/test_experiment_task.py tests/test_task_manager.py tests/test_api_experiment_benchmark.py -q --no-cov`，110 passed。
- 验证阶段重新构建 wheel 并执行 OpenSpec strict validation 和基线到当前 diff 的 whitespace 检查，均通过。
- review_mode=off 按 tweak 配置跳过自动独立审查。完整验证对照已完成：任务 2/2；规格场景 12/12；proposal 目标、所有者检查、终态保护、一致锁顺序、异常分支及 design 一致性符合要求。无需为 tweak 增补完整 Design Doc/plan。
- CRITICAL/IMPORTANT：无本次变更遗留问题。全量类型错误已在原基线复现，并明确列于下文。

## 已有问题与验证边界

全量 `python3 -m mypy src/ --ignore-missing-imports` 报告 5 个错误。在基线 commit 的独立临时副本运行同一命令复现完全相同结果，未新增类型错误：

- api/files/parsing.py:93：SafeLoader 为 Any。
- api/services/cost_service.py:278：metrics_rows 缺少类型注解。
- api/progress.py:139：unused-ignore。
- api/services/cost_alert_service.py:154：metrics 缺少类型注解。
- api/services/cost_alert_service.py:155：生成器 int 与 bool 不匹配。

broker 与模型调用使用替身，数据库、服务和 HTTP 接口使用真实实现。并发实测使用 SQLite；PostgreSQL 根据 SQL 和一致锁顺序检查，未连接 PostgreSQL 实例。没有前端代码变更，页面读取的任务/实验接口已通过刷新与删除回归；未将 HTTP 测试表述为浏览器实测。

review_mode 为 tweak 初始化的 off，按流程跳过自动独立代码审查；仍核对最终 diff 的所有者过滤、终态条件、锁顺序与异常分支。未发现新增安全问题或规格/设计漂移。

## Comet 阶段结果

build guard 13/13、verify guard 5/5 均通过。实现提交为 235d007 和 e62c5bf。

用户明确选择 C：归档、推送当前绑定分支并创建 PR。Comet 归档 6/6 步成功，delta 已按语义合并到 async-task-queue 主规格，主规格 strict 校验通过，change 已移动到 openspec/changes/archive/2026-10-28-experiment-cancellation-sync。归档状态 archived=true、branch_status=handled 已记录，最终 archive guard 6/6 通过。handled 表示已确认交付方式；推送和 PR 的实际结果以聊天最终链接为准。

归档提交仅包含本 change 的目录移动、主规格更新、状态证据及本报告；未包含无关工作区改动。
