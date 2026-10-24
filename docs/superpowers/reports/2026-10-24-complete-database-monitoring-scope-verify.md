# 数据库采集范围补齐验证

Change：complete-database-monitoring-scope。工作分支：comet/complete-database-monitoring-scope。

## 范围与流程
用户明确要求新建分支、继续 tweak、完成后归档并推送；按该授权执行。实际产品改动 7 个文件，其余为 OpenSpec/Comet 产物；保持单一 change，无数据库 schema、新端点或依赖变更。存在 delta spec，使用完整验证。review_mode=off 为 tweak 初始化值，跳过自动 reviewer；对最终 diff 进行人工正确性、安全和边界审查。

## 已完成检查
- 任务 1/1 已完成；proposal、design 和 delta 的两项需求、三个场景均有实现及测试。
- `python3 -m compileall -q api`：退出 0。
- 改动的 6 个 Python 文件通过 Ruff 与 Black 检查；`git diff --check` 通过。
- `comet classic openspec -- validate complete-database-monitoring-scope --strict`：通过。
- `pytest tests/test_api_monitoring.py tests/test_api_monitoring_database_metrics.py -q --no-cov`：71 passed。
- `pytest tests/test_api_database.py tests/test_api_monitoring_service.py tests/test_api_monitoring_store.py tests/test_api_monitoring_probes.py tests/test_api_monitoring_task_snapshots.py tests/test_api_experiment_benchmark.py tests/test_tasks_api.py -q --no-cov`：187 passed。
- `pytest tests/test_api_auth.py tests/test_api_files.py -q --no-cov`：136 passed。

## 规格与实现对照
- 独立业务来源：main 显式装配结果、实验、基准、A/B、成本 engine；MonitorService 同时绑定评估和 task engine。真实查询回归逐一执行成功与失败调用，验证各来源计数与错误数。
- 共享来源与进程范围：按 engine 对象去重；auth/file/monitoring 共用一个 SQLite 来源。HTTP 测试验证 8 个来源、用途、PID、当前进程范围及敏感值不进入响应；共享 engine 测试验证单次计数。
- 失败与关闭：SQLite 回归覆盖 Connection/Cursor、批量、脚本、唯一键错误、事务回滚、采集记录失败时保留结果与异常、缺口及关闭重开。原采集器测试覆盖窗口、有界裁剪、并发及 SQLAlchemy 关闭。没有保存 SQL、参数、URL、路径或异常正文。
- design 保留顶层评估口径、sources 分项统计、共享 SQLite 适配及有界进程内生命周期，均与最终实现一致，无 spec 漂移。tweak 不要求独立 Superpowers Design Doc 或完整 plan。

## 调试与验证说明
先运行新增来源测试，原实现因缺少 database_sources 失败；接入后通过。SQLite 测试初版将三次连接 PRAGMA 误计为四次，核对九个执行调用后更正预期为 9，未为此修改生产逻辑；随后相关测试全绿。一次命令引用不存在的测试文件导致未执行测试，已使用实际文件名重跑。

直接 `pytest -q --no-cov` 因 tests 包解析失败，在 test_api_monitoring_containers.py 与 test_api_monitoring_queue_health.py 收集阶段中断；改用 CI 相同的 `python3 -m pytest` 模块入口修正搜索路径，不改源码。`python3 -m pytest -q --no-cov -m "not online"`：3095 passed、8 skipped、127 warnings，退出 0，耗时 310.98 秒。警告包括现有 Pydantic/SQLAlchemy/pytest 弃用提示。

## 统计边界
仅当前 API 实例绑定来源，不包含 Celery/其他 API 进程/独立原生连接或数据库服务器全局流量。认证与文件为同一数据库，不按表分类。批量和脚本各记一次；延迟排除连接和抓取。各来源有独立内存上限，不聚合跨源 p95。SQLite 使用真实数据库验证；未声称完成实际 PostgreSQL 部署验证。

## 结论
PASS。任务、规格场景、编译、相关与全量离线测试及隐私边界均通过，无 CRITICAL/IMPORTANT/WARNING/SUGGESTION 待处理项。归档后按用户原始指令推送当前绑定分支，不创建 PR。

## PR #261 CI 类型检查修复
CI 的 Type Check 唯一错误为 `MeasuredSQLiteCursor.connection` 的静态类型是标准 `sqlite3.Connection`，无法识别自定义 `query_collectors`。已通过 `cast(MeasuredSQLiteConnection, self.connection)` 标明由连接工厂保证的具体类型；不改变查询执行或采集行为。

修复前使用 CI 命令复现该错误；本机默认环境另有两处基线类型错误，已在原始 main 快照复现。临时虚拟环境对齐 CI 的 mypy 2.4.0、types-PyYAML 6.0.12.20260906、redis 8.1.0 后，执行 `mypy src/ --ignore-missing-imports`：97 个源文件全部通过。监控与采集器回归 71 项通过；Ruff、Black 和 diff 检查通过。按用户确认仅在 PR 原分支修复，不关联其他活跃 change。
