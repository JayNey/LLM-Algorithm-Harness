# A/B 异步任务验证报告

结论：PASS。change `ab-test-async`，分支 `tweak/20261026/ab-test-async`，实现提交 `fd16f49`，基线 `33cff8d`。3/3 任务完成；2 项需求、11 个规格场景均有实现和回归证据。

## 最终行为
A/B run 通过 TaskManager 先提交数据库再发布 default 队列，返回持久化 task_id。worker 原子领取后解析用户密钥并执行 ABTestRunner；成功、失败、暂停、取消和完成时间同步到业务记录。API 重启保留未启动及活跃任务。并发启动、重复消息、发布超时和停止后收尾均受条件更新保护。父进程用唯一 execution_attempt 校验实际 claim 后处理 WorkerLostError，避免重复 child 的退出误伤原执行。前端保留 task_id，排队时显示等待提示并阻止重复启动和删除。

## 完整性与一致性
- 先落库、任务查询、并发启动及发布失败：`ABTestService.start_test`、`TaskManager.enqueue_task`；覆盖发布前第二连接可见、并发仅发布一次、发布期间已取消/完成、PostgreSQL 无匹配 CAS 不持锁的时序。
- 成功、失败与结果：`ABTestService._execute/_finish/results`、`run_ab_test_task`；真实临时数据库与 Celery trace 验证两层状态、时间、产物和错误。
- 用户隔离：API 404、worker 所有者和消息标识校验、失败信号不匹配拒绝写入均有测试。
- 重启：未启动、排队、运行、暂停关联的记录均被保留。
- 暂停/取消：TaskManager 同事务同步业务状态，runner 在题目入口检查停止信号，收尾不覆盖 paused/cancelled；串行及并行停止检查均有测试。
- 监控/日志：ab_test 在快照、耗时/成功率与隔离日志中被识别。
- worker 丢失：真实 Celery Request.on_failure、Request.execute 上下文传递和丢失重复 child 不误伤 claim-holder 均有回归。
- API 管理两个场景：HTTP 创建→202 task_id→统一任务查询→真实 worker→结果，以及跨用户隔离均通过。
- tweak 按用户 A+D 决策执行，复用现有架构；无数据库 schema 迁移、无新增依赖。设计与 delta spec 无漂移，无需完整 Superpowers Design Doc/plan。

## 验证证据
- 完整 `pytest`：3347 passed、11 skipped，覆盖率 92.44%。本次完整执行开始后追加了 PostgreSQL 无匹配 CAS 与执行 attempt 两项边界修复；它们及最终上下文/权限回归已包含在下述最新定向验证中，未把较早全量运行冒充为最终提交的全量复测。
- 最终全部受影响范围：230 passed。命令：`pytest tests/test_ab_test_task.py tests/test_utf8_io.py tests/test_async_task_submission.py tests/test_task_manager.py tests/test_api_experiment_benchmark.py tests/test_execution_logs.py tests/test_api_monitoring_task_snapshots.py tests/test_api_monitoring_service.py tests/test_ab_testing.py -q -o addopts=''`。
- 前端 `npm test`：257 passed；`npm run build`：通过；`npm run lint`：0 error。浏览器以隔离数据库和临时账号验证排队提示、无启动按钮、删除禁用，未修改开发者业务数据。
- `ruff check .`、`black --check .`、`python3 -m compileall -q api src`、`git diff --check`：通过。
- `mypy api/services/ab_test_service.py src/tasks/ab_test.py src/task_manager.py src/ab_testing.py --follow-imports=silent --ignore-missing-imports`：通过。
- `comet classic openspec -- validate ab-test-async --strict`：通过。
- 同一次只读集成审查及修复复核：无剩余 Important。审查员独立核对本机 Celery pool 上下文传递并运行 3 项关键回归，全部通过。

## 已有问题与验证边界
全量 mypy 的 5 个错误已在基线 `33cff8d` 独立副本复现：`api/files/parsing.py:93`、`api/services/cost_service.py:278`、`api/progress.py:139`、`api/services/cost_alert_service.py:154` 和 `:155`。前端 lint 的 2 个既有警告位于 BenchmarkDetailPage 的 hook 依赖；生产构建保留已有大 chunk 提示。本次未修改这些模块。

测试未连接生产 Redis 或模型提供商，外部消息传输、backend 和模型调用使用替身；数据库、Celery trace、父进程 Request 与浏览器页面使用真实实现。父进程整体退出或数据库不可用时无法立即持久化失败，本次未增加分布式心跳、执行租约或 A/B 暂停恢复能力。

## 归档状态
用户已明确选择 C：归档、推送当前绑定分支并创建 PR。归档后的两项主 spec 已通过 strict 校验；同时补齐实验管理主 spec 原有的 Purpose 占位文本，仅完善用途说明，不修改需求。规格已合并，change 已移至 openspec/changes/archive/2026-10-26-ab-test-async。验证报告和归档元数据纳入唯一归档提交；远端交付结果以聊天中的最终 PR 链接为准。
