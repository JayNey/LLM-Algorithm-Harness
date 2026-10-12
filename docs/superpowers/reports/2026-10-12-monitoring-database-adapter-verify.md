# PR #174 业务数据库监控适配验证报告

日期：2026-10-12（Asia/Shanghai）。本轮最终主线基线：`fa9ad3f`（#175/#151、#176/#156、#177 主线测试修复均已合并）。工作分支：`tweak/20261011/system-monitoring-foundation`，原基础实现报告保留在 2026-10-11 文件。

## 本轮实现

- 两次合入前进的 main，解决 create_app/import/router 参数冲突：保留 database_url 和实验/基准/A/B runner factory 参数，监控设置使用关键字 monitor_settings；保留最新路由和业务库启动/关闭流程。
- EvaluationService 提供只读 engine 属性。健康检查复用运行中的 engine，按当前 Base.metadata 以 SELECT 验证全部业务表/列，并动态核对 Alembic heads（兼容 #176 新模型和 0002 迁移）；不重建服务、不执行迁移、不触发 pending/running 恢复，也不泄露 URL/异常详情。
- 管理员任务快照读取持久化 Evaluation 表，分页最多 1000 条；总数/状态计数来自完整 SQL 聚合。SQLite 显式只读事务、PostgreSQL REPEATABLE READ 保证两次读取同一快照。数据库故障返回 unavailable/null，不伪记零任务。
- SQLAlchemy 采集真实游标执行次数、成功/错误、平均/P95 时延和速率，单 engine/单进程、有限窗口和行数；窗口不足/淘汰/采集缺口时主指标为 null、保留样本另行显示，不保存 SQL/参数/URL/异常。
- 固定 engine 转发器弱注册采集器，关闭时安全停止采集并释放采集器引用；转发器随 engine 回收。重复启停不增加监听或重复计数。
- 保留管理员/所有者权限、安全任务日志和已有配额。健康待接入项只保留 #149；真实队列/worker/LLM/缓存/容器指标及新日/月配额仍未实施，#157 保持开放。

## 调试与独立审查

合并后首先复现旧调用将 MonitorSettings 当 database_url，以及已移除 tasks/_tasks_lock 导致任务快照失败。修正调用并增加真实持久化状态、分页总数、健康探测不改变 pending 状态、重启恢复与参数兼容回归。

并发关闭审计证实直接 event.remove 会在正在派发的 SQLAlchemy 事件队列中触发 RuntimeError（deque mutated during iteration），改变原 SELECT 结果。以线程/Event 在 before/after 监听内部暂停并复现红灯，再改为固定弱注册转发器。真实 SELECT 在关闭期间仍成功；20 轮启停监听数量不增长，关闭的采集器和 disposed engine/转发器均可回收。

Bugbot 独立复审本轮完整 PR 差异及 #151 接口：**无新增缺陷**；审查者执行相关 **88 passed**。再合入 #176/#177 后补充复审通过，探针/HTTP **59 passed**；原三项凭据/CORS 发现保持修复。GitHub 未解决审查线程查询为空。

## 验证证据

- 本轮定向监控与 #151 数据库回归：**97 passed**；合入实验/基准主线后的最终集成回归：**119 passed**。
- 查询采集模块：**22 passed**，涵盖真实 SQLite 成功/失败、单调时钟窗口、淘汰/缺口、实例隔离、并发关闭、重复启停与回收。
- 最终全量离线：**1429 passed、4 skipped**，覆盖率 **93.78%**，90% 门禁不变。
- 实际 Runtime 检查：`comet check run system-monitoring-foundation build --local --timeout-ms 1800000 -- python -m pytest -m 'not online' --cov --cov-report=term --cov-report=xml -o faulthandler_timeout=60`，exit=0，116.92 秒；日志：`9ddfb216-a4c5-44a3-83a3-43bb19ce8bcf.log`。
- 在 fa79b5a 基线上曾全量 1407 passed/4 skipped、93.86%。新主线首轮在 Runtime 默认 300 秒上限被中止，无失败断言或诊断栈；加入 faulthandler 诊断的复跑正常完成，原 CORS 停点和并发关闭测试均通过，没有超时线程栈。第一次中止原因无法确认，未据此修改代码或降低门禁。
- Ruff、Black、文本显式编码扫描（0 处隐式编码）、OpenSpec strict 校验：通过。
- mypy src：87 文件通过；新增监控/路由类型检查：8 文件通过（follow-imports=silent）。

## 规格映射

- 新主线配置兼容、生命周期停采：test_database_config_positional_argument_and_metrics_lifecycle。
- 真实业务库/迁移、不改变任务：test_business_probe_reuses_engine_without_task_recovery_or_writes；test_business_probe_schema_and_migration_failure_never_echo_raw_details。
- 持久化分页/全量计数：test_task_snapshot_reports_real_simulator_state_and_filter；test_persistent_task_pages_have_accurate_full_counts_and_read_only_health。
- 重启状态与日志隔离：test_store_survives_restart_with_same_identity_scope；重启恢复行为遵从 #151，把中断的非终止任务明确标为 failed。
- 真实 SQL 成败与安全故障：test_actual_queries_errors_and_database_failure_are_explicit_without_secrets；采集器 callback/clock 失败安全测试。
- 并发关闭不改变原查询、弱引用回收：test_shutdown_during_listener_does_not_change_original_query 及重复启停/垃圾回收回归。

Proposal、design、delta specs 与实现一致，12 项任务全部完成；沿用用户指定的增量 Tweak，未采用完整 Classic 设计流程。完成后通过 Runtime 实际 build/verify 检查推进；归档与合并仍遵从既定流程。

## 限制与交付

- SQLite 与 HTTP 集成实际运行；PostgreSQL 本轮无实连接验证，不能把离线 SQL/边界检查当生产实测。
- 实际 Docker 最小预检仍返回 backend unavailable；没有回退 host，容器成功路径本机未实测。
- SQL 延迟仅 cursor 执行，不含连接池等待、fetch、完整事务或任务执行时长；连接获取失败不冒充已执行查询。样本只在当前采集器内存，重启清空，不声称跨进程全量。
- engine_role=evaluation_service 与持久化快照明确只覆盖评估服务；新实验/基准/A/B 服务的独立 engine 和任务类型没有并入这些计数，避免假称全局统计。
- engine 转发器首次安装须在请求开始前；关闭后转发器空操作，随 engine 生命周期回收，避免并发修改事件队列。
- 更新现有 PR #174，使用 Refs #157。最终提交的跨平台 CI 结果记录在 PR 描述，不自动合并。
