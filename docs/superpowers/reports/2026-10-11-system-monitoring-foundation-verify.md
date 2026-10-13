# Issue #157 系统监控基础验证报告

日期：2026-10-11（Asia/Shanghai）。基线：`6d32b3f`（#173 已合并）。分支：`tweak/20261011/system-monitoring-foundation`。

## 本次范围

- 操作者配置的管理员 UUID 白名单、会话认证与现有限流。
- 当前认证/文件 SQLite、主机 CPU/内存/磁盘、受控 Docker 预检与安全配置目录。
- 实际 HTTP 请求统计、错误率、平均/P95 时延、按方法与路由模板分组；持久化保留与采集缺口水位。
- 持久化脱敏生命周期事件、可信 TaskEvent 入口、所有者任务日志、筛选分页与管理员全局日志。
- 单事务快照 JSONL 下载、32 MiB 上限、实际导出/截断标记、暂存句柄关闭。
- 当前用户的真实文件/题库字节与条数、请求窗口、导入和传输限制。
- 未接入的队列、业务数据库、真实评估/LLM/容器指标与新日/月配额明确返回 not_configured/null。

## 验证证据

- 最终完整离线测试：**1370 passed、4 skipped**，覆盖率 **93.71%**，90% 门禁保持不变。
- Runtime 实际执行 `comet check run system-monitoring-foundation build --local -- python -m pytest -m 'not online' --cov --cov-report=term --cov-report=xml`，exit=0；日志 `d79e9360-017a-490b-8727-9ec07b9e8791.log`。
- 独立审查者最终执行 secrets 与 HTTP 监控测试：**51 passed**；根代理针对脱敏与 CORS 的最终回归：**12 passed**。
- Ruff、Black、显式文本编码扫描（0 处隐式编码）、OpenSpec strict 校验：通过。
- `mypy src/ --ignore-missing-imports`：87 文件通过；新增监控/路由及认证依赖额外类型检查：8 文件通过（follow-imports=silent）。
- 实际 Docker 预检返回 backend unavailable；成功执行路径采用边界模拟验证，本机未实测 Docker 容器成功运行，没有回退 host。

## 调试和独立审查

先复现原沙箱预检将 timeout、错误答案、空结果和不一致汇总判为健康的四个失败用例，再修复统一执行器；CLI 与 API 复用相同判定。详细健康检查在已执行的 Docker/SQLite 探测失败时返回 degraded。

实现期间补充请求采集失败水位、单次快照有界导出及客户端断开后的暂存句柄关闭；可信 UUID 选择器保留原值，避免合法短密钥将所有者索引替换掉。

Bugbot 初审发现 P1：先替换已知密钥可能破坏 password/api_key 等字段识别，使另一凭据原文入库；P2：外层 CORS 直接处理的成功/失败预检没有记录。均用失败测试复现，分别调整脱敏顺序和 ASGI 包装顺序。

复审又发现包含 `[REDACTED]` 的合法完整密钥被分段替换遗漏。改为先识别凭据字段，再一次匹配完整密钥和占位符、较长值优先；补 SQLite 和下载回归。最终独立复审通过，无未解决发现。使用用户既定增量流程与人工安排的 Bugbot 审查，未采用完整 Classic 设计流程。

## 规格与设计映射

- 管理员与所有者隔离：`test_system_routes_require_authenticated_operator`、`test_operator_identity_is_not_username_or_token_role`、`test_task_logs_download_redaction_and_active_owner_mapping`。
- 真实状态与未配置依赖：`test_health_sources_and_safe_admin_configuration`、probes 的真实数据库/资源与缓存边界测试；模拟任务明确标注来源。
- 持久化安全日志：`test_logs_are_redacted_before_persistence_and_bounded`、`test_log_filtering_pagination_and_literal_search`、`test_log_export_uses_one_snapshot_and_owner_filters`、`test_log_export_byte_cap_preserves_whole_unicode_lines`、`test_download_closes_temporary_file_on_client_disconnect`。
- 统计完整性：`test_startup_and_truncation_never_claim_complete_totals`、`test_failed_capture_remembers_gap_until_database_recovers`、`test_endpoint_statistics_group_methods_and_preserve_incomplete_sample`、`test_cors_preflight_responses_are_included_in_actual_metrics`。
- 并发和重启：SQLite 多线程/多实例/spawn 多进程记录、重启持久化及共享水位测试。
- 现有配额：`test_quotas_are_owned_and_count_actual_sql_utf8_bytes`、`test_quota_view_matches_enforced_file_limit_and_expired_rates`。
- 预检成功/失败：`test_health_check_delegates_to_real_execution_path`、`test_health_check_rejects_unsuccessful_known_good_probe`，与 sandbox-preflight delta spec 一致。
- 凭据边界：syntax-shaped key、重叠密钥、占位符密钥的 helper/实际存储/HTTP 下载测试。

Proposal、design、两个 delta specs 与本次实现范围一致；八项任务完成。Tweak 使用 change 内 design.md，无需额外完整设计产物。

## 接入限制与交付

#149 与 #151 尚未合并实现，因此 #157 本次只交付可用基础，PR 使用 `Refs #157`。后续仍需真实 Redis/Celery、业务数据库连通性/性能、worker 输出与 LLM 指标、集群任务状态、容器资源和日/月配额策略。

当前 TaskEvent 为可信服务端入口，没有开放 HTTP 任意所有者日志写入；缓存只在绑定实际实例后提供统计。API 任务快照来自已有进程内模拟器。SQLite 完全不可写且进程同时终止时，尚未落盘的采集缺口不能跨重启恢复；日志为有界运维记录，保留期之外的历史不能下载。

提交关联基础 PR，全部平台最终 CI 以 PR 最新提交为准，并记录在 PR 描述。归档与合并保持用户既定流程。
