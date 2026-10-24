# LLM 统计窗口查询验证报告

日期：2026-10-23。Change：llm-stats-window。分支：comet/llm-stats-window。

## 结论
PASS。3/3 任务完成，三个要求及六个场景有实现与验证证据，设计与规格一致，无本次引入的 CRITICAL/IMPORTANT 或待接受偏差。全量 3082 passed、8 skipped，覆盖率 92.01%，达到项目 90% 门槛。

## 完整性与规格覆盖
- 三个任务覆盖存储、接口及最终验证；用户选择 2A，按新分支与 tweak 处理现有接口窗口扩展和对应数据记录。最终涉及八个代码/测试/说明文件及 Comet 产物，范围仍是同一项统计能力。
- 时间窗口和边界：test_llm_window_uses_completion_time_and_inclusive_boundaries 验证窗口前、起点、内部、终点及未来记录，仅三条入窗；两次成功一次失败，平均 200ms。
- 空窗口与参数权限：test_llm_window_empty_and_startup_do_not_invent_history 验证完整空窗口为零/null；test_llm_window_query_filters_real_records_and_keeps_cumulative_default 验证 HTTP 401/403、窗口内两次调用、50% 成功率、200ms 平均耗时、无参数三次累计、1/86400 合法及非法参数 400、no-store。
- 采集启动与旧库升级：test_llm_window_upgrade_preserves_cumulative_without_backfill 验证旧累计不变、历史不回填、采集前窗口不完整。
- 清理与重启：test_llm_window_pruning_survives_restart_without_losing_cumulative 分别验证行数/时限清理、持久化水位、保留样本、累计不受影响及后续窗口恢复完整。并发与 spawn 进程测试验证窗口记录和累计均可跨连接读取。
- 故障隔离与隐私：现有真实 SDK 边界采集回归涵盖重试、缓存、验证、计时/持久化故障隔离；存储测试确认窗口行全部为数值，无提示、响应、凭证、端点或错误正文。

## 正确性与设计一致性
- 记录时间为完成尝试写入采集入口时的 Unix 时间；按两端包含的区间过滤，失败尝试也计入平均延迟。
- 新记录表与累计更新同一事务提交；窗口查询在同一事务清理、读取水位与 SQL 聚合，避免读取不一致。
- 沿用 retention_seconds/max_rows；删除水位独立且持久化，不完整窗口主指标 null，retained_sample 明示剩余样本。
- 默认无参数与 performance 继续累计口径；用量登记/密钥验证为独立累计字段，文档明确。
- 升级无需外部迁移或依赖，初始化创建有界数值记录表。API 和 worker 需统一升级；best-effort 不保证无采集遗漏。设计与 delta spec 无漂移。
- tweak 只需 change/design.md，不生成独立 Superpowers Design Doc/plan。按持久化 review_mode=off 跳过自动独立审查，主会话已检查最终 diff、SQL 参数化、权限和保留边界。

## 已执行验证
- RED：11 项存储窗口测试因缺失窗口参数失败；HTTP 窗口测试因原路由忽略参数而缺少 window_complete 失败，确认是目标能力缺失后实现。
- 相关最终回归命令：python3 -m pytest tests/test_api_monitoring_store.py tests/test_api_monitoring.py tests/test_api_monitoring_service.py tests/test_api_documentation.py tests/test_api_versioning.py tests/test_llm_call_metrics.py tests/test_llm_client.py tests/test_llm_client_cache.py tests/unit/test_api_endpoints.py -q --no-cov：1049 passed，22 项既有弃用提示。
- black --check 与 ruff check 对六个 Python 修改文件通过；git diff --check 通过。
- mypy api/monitoring/store.py --follow-imports=silent：通过。
- python3 -m compileall -q api src：通过。
- python3 scripts/find_missing_encoding.py：Implicit text encodings: 0。
- python3 -m pip wheel . --no-deps --no-build-isolation --wheel-dir /tmp/llm-window-wheel：构建成功。
- comet classic openspec -- validate llm-stats-window --strict：通过。

- 全量 CI 入口：python3 -m pytest -m 'not online'：3082 passed、8 skipped、127 warnings，377.79 秒；总覆盖率 92.01%，退出码 0。跳过项为测试既有环境/在线资源条件，未为本次修改新增跳过或降低覆盖率门槛。

## 环境记录
直接 pytest -m 'not online' 在 tests/test_api_monitoring_containers.py 与 tests/test_api_monitoring_queue_health.py 收集时因 tests 包路径失败；与此前采集 change 的已知环境问题一致，改用 CI 的 python3 -m pytest 入口重跑，无需修改源码。Comet task 插件尝试写全局状态锁遭遇 EPERM，按技能规定不阻塞主流程。

## 阶段状态与交付
实现提交：9e83c85、8bd680b；任务验证记录提交：5726173。build guard 13 项、verify guard 5 项全部通过，archive 入口检查 5 项通过。verify_mode=full、verify_result=pass、phase=archive、branch_status=pending。
未提交内容只有本报告及当前 change 的 Comet 状态/轨迹，均属于本次流程。用户已明确选择 C：确认归档、推送当前绑定分支并创建 PR。交付按该授权继续执行。

归档确认后：comet archive llm-stats-window 成功完成 6/6 步，主规格已同步，change 位于 openspec/changes/archive/2026-10-23-llm-stats-window。最终 archive guard 六项通过，archived=true、verify_result=pass、branch_status=handled。handled 记录已确认的交付方式；推送与 PR 创建随后执行。
