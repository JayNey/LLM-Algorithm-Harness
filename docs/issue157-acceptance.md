# #157 系统监控 API 逐项验收

范围：原 [issue #157](https://github.com/JayNey/LLM-Algorithm-Harness/issues/157) 的44个复选条目。核对基线 main `0e795e4b4ac91e4d00b1f0f60a1e9d6f50d3090d`，已包含#269；本轮只修正旧交付状态标记、OpenAPI例子及文档。下列勾选表示代码能力/列明回归已覆盖，不表示所有生产环境、完整集群或真实提供商均已验证。当前执行证据与限制见 [本轮验证报告](superpowers/reports/2026-10-25-monitoring-acceptance-verify.md)。

## 1. 系统健康检查（7项）

代码：[监控路由](../api/routes/monitoring.py)、[探针](../api/monitoring/probes.py)。回归：[HTTP](../tests/test_api_monitoring.py)、[本机探针](../tests/test_api_monitoring_probes.py)、[队列](../tests/test_api_monitoring_queue_health.py)。

- [x] 整体健康：公开 `/api/v1/health` 仅存活；管理员 `/system/health` 汇总真实探测。`test_health_sources_and_safe_admin_configuration` 验证两者分离。
- [x] 数据库连接：认证/文件SQLite与实际业务engine、表和Alembic版本均检查；失败不泄露连接串。`test_sqlite_probe_checks_real_connection_and_tables`、`test_business_probe_reuses_engine_without_task_recovery_or_writes`。
- [x] Redis连接：显式启用后对实际broker执行有界PING；禁用/失败/超时有独立状态。`test_real_child_protocol_cache_age_expiry_and_secret_filter`、真实依赖证据。
- [x] Celery worker：只读自定义命令返回回复节点的数值计数，超时不冒充空集。`test_worker_command_counts_sets_without_inspecting_request_data`、真实依赖证据。
- [x] Docker沙箱可用性：API复用 `SandboxExecutor.health_check()` 的实际执行预检，仅Docker，不回退宿主机。`test_sandbox_uses_only_docker_and_safe_error_then_expires`、真实预检证据。
- [x] 磁盘空间：测量上传文件系统真实容量/用量，登记文件另计。`test_resources_measure_actual_host_without_paths`、`test_registered_storage_aggregates_live_files_and_excludes_deleted`。
- [x] 内存使用：psutil主机读数及失败unknown，无虚构零值。`test_psutil_failure_returns_unknown_without_fake_zero_or_exception`。

## 2. 系统状态监控（6项）

代码：[任务快照](../api/monitoring/task_snapshots.py)、[队列观测](../api/monitoring/queue_probe.py)、[容器采集](../api/monitoring/containers.py)、[持久化指标](../api/monitoring/store.py)。

- [x] 当前运行任务数：旧评估与AsyncTask分来源、全量计数与分页同事务；已关联任务不双计。`test_linked_evaluation_is_not_counted_as_legacy_task`、`test_counts_cover_matching_source_before_pagination`。
- [x] 排队任务数：数据库pending、broker各优先级分桶等待数、worker reserved独立展示，不相加。`test_status_separates_broker_pending_and_reserved`、`test_broker_waiting_counts_all_priority_buckets_without_consuming`。
- [x] Worker负载：active/reserved/concurrency只聚合有效回复，截断/异常保持partial/null，不推算CPU。`test_invalid_counts_are_partial_and_never_aggregated_as_zero`。
- [x] Docker容器资源：只读ps/stats观察固定标签范围的CPU、内存、限额、PIDs，ID摘要与样本上限明确。`test_safe_metrics_only_and_fixed_readonly_commands`、真实带/不带标签及退出竞态证据。
- [x] API QPS/响应时间：实际ASGI最终响应、方法和路由模板持久化，窗口不完整只给保留样本。`test_endpoint_statistics_group_methods_and_preserve_incomplete_sample`、`test_asgi_latency_excludes_work_after_completed_response`。
- [x] 错误率：HTTP4xx/5xx除以已捕获窗口样本；采集失败、清理与起点可见。`test_failed_capture_remembers_gap_until_database_recovers`、`test_cors_preflight_responses_are_included_in_actual_metrics`。

## 3. 日志管理（5项）

代码：[安全日志存储](../api/monitoring/store.py)、[worker事件](../api/monitoring/execution_logs.py)、[路由](../api/routes/monitoring.py)。回归：[worker日志](../tests/test_execution_logs.py)、[日志存储](../tests/test_api_monitoring_store.py)。

- [x] 任务执行日志：worker在提交后的可信任务行取归属，异步ID、评估ID及旧run映射隔离；支持四类业务任务。`test_committed_worker_states_are_owned_and_downloadable`、`test_real_evaluation_worker_records_units`。
- [x] 日志级别：DEBUG/INFO/WARNING/ERROR/CRITICAL规范化，非法级别拒绝。`test_invalid_log_filters_are_client_errors`。
- [x] 时间范围：带时区ISO8601，起止顺序及epoch边界校验。`test_log_query_rejects_invalid_ranges`、`test_legacy_collision_is_separate_and_time_pagination_export_match`。
- [x] 搜索：脱敏消息的有界字面子串，通配符不变成SQL表达式。`test_log_filtering_pagination_and_literal_search`。
- [x] 下载：所有权校验后的JSONL文本、单事务快照、32MiB上限和截断头；断开也关闭暂存句柄。`test_log_export_uses_one_snapshot_and_owner_filters`、`test_log_export_byte_cap_preserves_whole_unicode_lines`、`test_download_closes_temporary_file_on_client_disconnect`。

## 4. 性能指标（5项）

代码：[服务聚合](../api/monitoring/service.py)、[数据库指标](../api/monitoring/database_metrics.py)、[LLM采集](../api/monitoring/llm_metrics.py)。

- [x] 任务平均执行时间：持久化首次开始至最终结束的墙钟秒数，四类任务分组，包含暂停/重试间隔；无样本null。`test_performance_aggregates_persisted_execution_times`、`test_performance_empty_and_unavailable`。
- [x] API端点耗时：按HTTP方法/模板聚合均值/P95，排除发送完响应后的后台工作。`test_endpoint_statistics_group_methods_and_preserve_incomplete_sample`、`test_asgi_latency_excludes_work_after_completed_response`。
- [x] 数据库查询：绑定的业务engine和auth/file SQLite分来源、去重、成功/错误/时延；只覆盖当前API进程，不保存SQL/参数。`test_database_sources_cover_independent_engines_and_shared_sqlite`、`test_monitor_deduplicates_shared_engines`、`test_sqlite_calls_preserve_transactions_and_isolate_capture_failure`。
- [x] 缓存命中率：实际LLMClient共享快照，先汇总hit/miss再相除；TTL、容量去重和fork边界明确。`test_worker_cache_overall_rate_weights_cross_process_counts`、`test_worker_cache_fork_does_not_duplicate_parent_counts`。
- [x] LLM调用：真实SDK尝试成功/失败/重试及排除退避的耗时；累计和可选窗口，缓存/连接验证不计。`test_generation_outcomes_at_provider_boundary`、`test_real_openai_sdk_transport_retry_is_observed`、`test_llm_window_uses_completion_time_and_inclusive_boundaries`。SDK传输由测试替身提供，未付费调用真实模型。

## 5. 资源配额（4项）

代码：[用户配额视图](../api/monitoring/service.py)、[并发准入](../tests/test_user_evaluation_concurrency.py)、[调用额度](../tests/test_user_call_limits.py)。

- [x] 当前用户用量：两个quotas别名只读认证主体，不接受他人user_id覆盖。`test_calendar_quota_fields_and_owner_isolation`、`test_evaluation_concurrency_quota_aliases_are_authenticated_and_owner_scoped`。
- [x] 并发任务限制：每用户pending/running评估的原子准入与剩余额度，发布失败回滚，跨进程不超发。`test_independent_processes_share_one_remaining_slot`、`test_publish_failure_releases_capacity`。
- [x] 存储空间：真实登记文件字节（含待清理）、个人题库UTF8字节/条数分别计算并展示实际限制。`test_quotas_are_owned_and_count_actual_sql_utf8_bytes`、`test_quota_view_matches_enforced_file_limit_and_expired_rates`。
- [x] 每日/月调用：明确为用户LLM生成SDK尝试，不是所有HTTP请求；UTC自然周期、重试计量、两周期原子准入，有限enforced/无限metered。`test_processes_share_the_same_admission_limit`、`test_quota_query_resets_at_utc_calendar_boundary`、`test_calendar_rollover_restart_and_owners`。

## 6. 系统配置（4项）

代码：[白名单](../api/monitoring/config.py)、[配置路由](../api/routes/monitoring.py)、[静态目录](../api/monitoring/probes.py)。#269已合入，无重复实现。

- [x] 当前生效配置：`/system/config`读当前服务持有对象，固定数值/布尔/可空额度白名单，无探测/环境重读。`test_system_config_returns_loaded_values_without_probes`。
- [x] 策略目录：复用实际STRATEGY_MAP和StrategyConfig默认资源参数，排除提示/自定义参数。`test_strategy_directory_reuses_registry_and_schema_defaults`。
- [x] 提供商/模型：支持类型和固定公开示例目录，显式offline、不保证当前模型可用。`test_providers_catalog_is_offline_and_config_view_has_no_secrets`。
- [x] 沙箱配置：展示受控Docker配置的公开子集，不返回宿主路径/环境。`test_health_sources_and_safe_admin_configuration`。

## 7. 既有模块集成（4项）

- [x] 沙箱预检：CLI与API使用同一执行器健康判定；`test_health_check_delegates_to_real_execution_path`、`test_health_check_rejects_unsuccessful_known_good_probe`及真实HTTP/执行器预检。
- [x] 日志系统：复用结构化日志/脱敏组件；worker事件在API无订阅者时仍持久化，采集故障不改任务结果。`test_independent_worker_process_events_persist`、`test_logging_failure_does_not_change_task_or_leak_error`、[日志配置测试](../tests/test_api_logging_config.py)。
- [x] 任务服务：绑定本应用实际任务engine，只读快照不触发恢复/重新调度/外部轮询。`test_source_queries_are_read_only_and_bound_to_actual_engine`、[队列兼容测试](../tests/test_api_monitoring_queue_compatibility.py)。
- [x] 缓存：真实LLMClient读取/写入自动上报，保留可信单实例兼容视图；`test_worker_cache_real_client_shared_collection`、`test_worker_cache_expired_entry_is_miss`。

## 8. 安全约束（3项）

- [x] 管理员：服务端实时UUID配置、有效会话和已有权限守卫；客户端角色/用户名不可提权。`test_system_routes_require_authenticated_operator`、`test_operator_identity_is_not_username_or_token_role`、`test_system_config_requires_live_administrator`。
- [x] 日志秘密：入库前凭据脱敏、上下文白名单和大小限制；其他用户/不存在资源一致404。`test_syntax_shaped_user_key_cannot_expose_other_log_credentials`、`test_literal_placeholder_inside_known_key_is_removed_from_task_logs`、`test_writer_redacts_before_storage_and_ignores_raw_payload`。
- [x] 配置秘密：凭据/URL/路径/管理员列表/未知扩展完全不输出，no-store。`test_system_config_excludes_sensitive_and_future_fields`。

## 9. 验收标准（6项）

- [x] 健康准确：公开存活和管理员深度探测区分，失败/禁用不伪装healthy；新回归验证空pending不抹去partial/degraded。
- [x] 状态更新：任务读已提交数据，外部探测有界TTL及年龄，不将缓存/部分回复称为全局即时原子快照。
- [x] 日志查询过滤：级别、时间、字面搜索、分页和下载均有实际SQLite/HTTP回归。
- [x] 指标准确：样本覆盖/清理/故障显式；任务、SQL、SDK及缓存有独立数据源、单位和范围，不伪造缺测或合并不同口径。
- [x] 沙箱一致：同一Docker执行路径的预检及受限容器资源采集有真实本机验证；无宿主回退。
- [x] 无日志凭据泄露：原始秘密不进入持久化、查询或下载；并行/重启/所有者边界均有回归。该结论限已列测试边界，不宣称任意未来凭据格式或全系统形式证明。

## 交付与部署边界

- 代码具备和运维部署就绪分开验收。`pending_issues=[]`仅清除旧代码交付标记；Redis/Docker默认禁用仍partial，数据库失败仍degraded，模型执行就绪仍null。
- API、worker需加载一致配置并共享对应认证/业务存储。数据库查询指标仅当前API；worker/cache/LLM只覆盖实际回复或成功采集范围；Docker只覆盖当前context的带标签容器。
- 当前实跑层级：临时SQLite与HTTP、隔离Redis/Celery只读观测、实际Docker预检和自建容器资源。未验证生产集群、真实模型端到端、实际PostgreSQL部署或Windows Docker daemon；具体命令、退出码与资源清理见本轮报告。
- 先审查并合入本收尾PR，再由维护者确认关闭#157。清单勾选不修改GitHub issue，也不替代PR最新头CI。

## 一键复现当前真实依赖观测

环境需提供Docker daemon和已缓存的`python:3.11-slim`、`redis:7-alpine`镜像，以及已安装项目依赖的Python。运行：

```bash
.venv/bin/python scripts/verify_monitoring_acceptance.py --run-live \
  --output docs/superpowers/reports/assets/monitoring-acceptance-2026-10-25/actual-dependencies.json
```

脚本先运行现有带/不带标签容器资源集成测试，再创建仅绑定127.0.0.1随机端口的临时Redis、独立solo worker及临时API/SQLite。它注册临时测试身份、执行只读健康/资源/配额请求，不提交业务任务或调用提供商。Redis使用唯一名称和本轮所有权标签，清理前检查标签；私有日志保存在新建临时目录，`--output`只接收脱敏JSON。失败和清理未确认均退出非零并记录失败，不把未知状态写为通过。

本轮在macOS主机的Linux Docker daemon实际执行；脚本和探针不因此被声明已在真实Windows Docker或生产环境通过。
