# 用户评估并发查询验证

日期：2026-10-24。Change：`user-evaluation-concurrency-query`。分支：`codex/user-evaluation-concurrency-query`。基线：`6ce307cd26db2350124afee43bbe52350b1edd3c`。实现提交：`92e43dd`、`95c053d`。

## 验收结果

- 完整性：3/3 tasks 完成；既有 api/evaluation-execution 能力增加额度查询 delta，未新建端点或数据库 schema。
- 正确性：MonitorService.quotas 使用 task_engine 执行一次 SELECT COUNT，限定认证用户、evaluation 类型、pending/running 状态；与 TaskManager 准入配置和计数条件一致。真实 used 不截断，remaining 最低为 0。两个配额别名沿用认证与 no-store。
- 一致性：proposal、精简 design、delta spec 和实现无漂移；本次为 tweak，不需要完整 Superpowers Design Doc/plan。产品代码/文档/测试共 5 个文件，其他改动为本 change 的工作流产物。

## 场景证据

1. 空闲及自定义限额：`test_evaluation_quota_counts_admitted_tasks_and_preserves_over_limit` 分别使用限额 1、2、3，覆盖零用量、两个活动任务和历史超限。
2. 状态/类型/所有者：上述测试同时覆盖 pending/running、paused/completed/failed/cancelled、其他用户、其他任务类型与无 AsyncTask 的草稿。
3. 状态提交后刷新：`test_evaluation_quota_reflects_committed_status_changes_without_writes` 覆盖四种释放状态以及恢复 pending；事件监听确认额度读取仅一次 SELECT。
4. 独立任务库及故障：`test_evaluation_quota_uses_separate_task_engine_and_propagates_db_failure` 使用独立 SQLite engine，并确认丢失任务表时抛出数据库异常，不返回零额度。
5. 两个 HTTP 别名：`test_evaluation_concurrency_quota_aliases_are_authenticated_and_owner_scoped` 确认 401、普通用户可查询自己、参数不可越权、no-store、禁止 Celery 轮询/发布及 OpenAPI 示例字段。

## 实际验证

- RED：新增 8 项服务测试均因缺少 evaluation_concurrency 而失败，日志 `/private/tmp/evaluation-quota-red.log`；新增 2 项 HTTP 测试因文档示例缺字段失败，日志 `/private/tmp/evaluation-quota-http-red.log`。
- GREEN：服务层 19 passed；综合相关回归 111 passed（22 条既有弃用警告），命令 `python3 -m pytest tests/test_api_monitoring.py tests/test_api_documentation.py tests/test_user_evaluation_concurrency.py tests/test_api_monitoring_service.py -q --no-cov`，日志 `/private/tmp/evaluation-quota-targeted.log`。
- `ruff check .`、`black --check .`（338 files unchanged）、`python3 -m compileall -q api src`、`git diff --check` 与 OpenSpec strict validate 均通过。
- 全量离线回归：`python3 -m pytest -m 'not online'`，3126 passed、8 skipped、127 warnings，耗时 395.16 秒，覆盖率 92.05%，通过 90% 门槛；日志 `/private/tmp/evaluation-quota-full.log`。

## 最终集成审查

独立只读 reviewer 审查最终代码、文档、测试与规格，无需修复的正确性、安全或边界问题。核对与准入一致、独立 task_engine、认证主体、超限归零、故障传播、SELECT 只读及无 Celery 调用；未重复派发最终审查。

## 限制

额度是查询时的数据库快照，不预留名额；不能保证下次提交时仍有容量。SQLAlchemy 查询可用于 SQLite/PostgreSQL，本次实际查询和状态变化测试使用 SQLite，未声称执行真实 PostgreSQL 集成验证。数据库错误沿用统一 500 处理，不伪造可用容量。

结论：PASS。完整性、正确性、一致性、构建、测试、安全与独立集成审查均通过。
