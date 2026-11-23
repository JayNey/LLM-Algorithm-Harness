# Issue #511 验证报告

## 候选与结论

Change：`fix-queued-evaluation-delete`；实施及首次验收分支：`main`；用户选择 PR 交付后绑定 `codex/fix-queued-evaluation-delete`，实现内容未改变、原检查仍适用；基线：`e4e37886f98ec2b9e2a7a8fdd36d32bf95b2c883`。差异仅涉及 5 个交付文件及本 change 的工作流产物，无 schema、依赖或前端结构变更。

已入队评估的删除现在会在任何文件清理之前被拒绝，`can_delete` 与持久化活动任务一致。提交与删除共享事务锁，取消但仍有在途执行时仍不能删除。停止后的删除保留既有结果级联、文件清理、防复活与额度释放语义。

| 维度 | 核对结果 |
| --- | --- |
| 完整性 | 6 项任务逐项核对；2 条新增要求、7 个场景都有实现及回归依据 |
| 正确性 | 活动任务/归属/过期链接、响应能力、事务竞争及资源清理与 delta spec 一致 |
| 一致性 | 复用既有准入数据库锁、任务/评估加锁顺序、非阻塞执行权和文件删除机制 |

## 场景映射

| Delta spec 场景 | 实现与测试依据 |
| --- | --- |
| 已入队 pending 评估拒绝删除 | `EvaluationService._delete_evaluation` 在清理前检查 owned 活动任务；`test_queued_evaluation_delete_preserves_files_until_cancelled_and_stopped` 验证 HTTP 400、保留任务/结果/文件及原额度占用 |
| 活动任务优先于可删除业务状态 | `_live_evaluation_task_filter`、`_operation_capabilities` 及列表批量加载；`test_active_task_blocks_delete_before_cleanup`、`test_delete_capability_matches_persisted_activity` 覆盖状态组合；`test_delete_finds_active_tasks_without_current_link` 覆盖链接缺失及过期；`test_unrelated_task_does_not_block_delete` 覆盖所有者、实体及类型隔离 |
| 取消停止后删除与额度释放 | HTTP 集成回归验证额度从 1 到 0，业务记录与结果删除、文件清理、终态任务保留，延迟文件发布返回 404；异步入口只删除 owned 终态任务 |
| 提交先于删除取得互斥权 | `test_start_owns_transaction_before_delete_rechecks_activity` 暂停在提交事务内，删除在取得准入锁后重新检查并拒绝，无清理副作用 |
| 删除先于提交取得互斥权 | `test_delete_owns_transaction_through_cleanup_against_start` 在清理回调内启动竞争请求，验证启动回滚且不发布消息、不遗留 AsyncTask |
| 取消后仍有在途执行 | `test_cancelled_but_still_executing_cannot_be_deleted` 覆盖两个服务入口，HTTP 集成回归同时验证未清理文件，执行权释放后可成功删除 |
| 清理失败可重试 | `test_cleanup_failure_keeps_evaluation_and_releases_locks` 验证失败保留评估并释放事务锁与执行权，重试成功 |

额外检查：`test_list_loads_linked_tasks_in_one_query` 保持批量查询；响应投影不调用 broker；`test_postgresql_delete_uses_admission_lock_without_capacity_check` 验证提交/删除使用同一个用户锁 key，且删除不受满额度限制。既有评估与 worker 回归覆盖领取、恢复、取消、重复消息及产物防复活。

## 真实执行记录

工作目录均为 `/Users/verstappen/LLM-Algorithm-Harness`，Python 为项目 `.venv/bin/python`。

1. **RED：** 首批状态与投影回归为 20 failed、12 passed；失败来自活动任务仍被删除、`can_delete` 仍为 true。并发/执行停止/PG 锁回归 5 failed；异步入口回归 1 failed（未抛出活动任务错误，取消方法已 mock，不访问 broker）。日志：`/tmp/issue511-red.log`、`/tmp/issue511-race-red.log`、`/tmp/issue511-async-red.log`。
2. **关联回归：** `MPLCONFIGDIR=/tmp/issue511-mpl .venv/bin/python -m pytest tests/test_evaluation_workflow_contract.py tests/test_evaluation_service_async.py tests/test_user_evaluation_concurrency.py tests/test_api_files.py tests/test_api_evaluations.py tests/test_api_database.py tests/test_evaluation_async_flow.py tests/test_celery_tasks.py tests/test_task_manager.py tests/test_evaluation_artifacts.py --no-cov -q`。原运行 463 passed、1 skipped、1 failed，唯一失败为现有 broker 测试在 `socket.bind(127.0.0.1, 0)` 被沙箱权限拒绝。将该用例在允许本机端口的环境单独执行后 **1 passed**，合计 **464 passed、1 skipped**。日志：`/tmp/issue511-regression.log`、`/tmp/issue511-broker-check.log`。
3. **最终候选专项：** 对谓词的类型整理后，重跑上述前四个文件中删除、管理能力、批量查询及事务竞争用例，**54 passed**。日志：`/tmp/issue511-final-focused.log`。其余改动不影响前一次广泛回归的证据适用性。
4. **静态检查：** 5 个改动 Python 文件的 `.venv/bin/ruff check`、`.venv/bin/black --check` 和 `git diff --check` 通过。
5. **类型检查：** `.venv/bin/mypy api/services/evaluation_service.py src/task_manager.py --follow-imports=silent --disable-error-code=import-untyped`：2 个源文件无问题。未屏蔽改动代码的类型错误；`import-untyped` 排除仅针对当前环境缺少 Celery/scipy 类型桩。首次暴露的本次代码类型问题已修正。
6. **规格检查：** `comet classic openspec -- validate fix-queued-evaluation-delete --strict` 通过。

结构化证据见本 change 的 `checks.json`，说明页见 `walkthrough.html`。测试生成的空执行锁文件已在测试结束后清理，无运行数据混入交付。

## 审查与验证边界

- 当前 tweak Run 为 `direct/direct/off`；已完成实施者对最终 diff、规格和设计的一致性核对，独立 reviewer 按 `reviewMode=off` 未执行，未将自检标为独立验收。
- `TEST_POSTGRESQL_URL` 未配置，因此真实 PostgreSQL 连接池测试跳过，未宣称真实 PG 并发验收通过。锁 key、SQL 绑定和顺序通过真实 Session 拦截 PG 特有 SQL 的契约测试覆盖，双向竞争使用实际 SQLite 数据库。
- 本次未进行真实付费模型调用、生产操作或历史孤立任务修复。文件库和业务库仍非分布式事务，清理异常保留业务记录供重试，沿用已批准的设计边界。
- 无未解决的 CRITICAL/IMPORTANT、规格偏差或新增范围；仍处于已批准 tweak 范围内。Run 验证与归档状态以 Comet 后续收据为准。
