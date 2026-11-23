# restrict-web-alert-targets 验证报告

日期：2026-11-23。工作区：`/Users/verstappen/LLM-Algorithm-Harness`，分支 `main`，基线 `e7deb9f77f8c4d06039e926f4821b766ece0278d`。

## 结论

已完成批准范围内的实现与验收：6/6 任务，2/2 新增需求，7/7 场景有实现及测试证据。未发现 CRITICAL、IMPORTANT、WARNING 或 SUGGESTION 问题。可进入 Archive 的交付决定；本报告不代表归档、提交或推送已经获准。

| 维度 | 结果 |
| --- | --- |
| 完整性 | tasks.md 6/6 完成；实际交付文件 6 个，与批准范围一致 |
| 正确性 | 2 项 delta requirement、7 个 scenario 全部覆盖；146 项相关测试通过 |
| 一致性 | 共享部署策略、最终规则状态校验、投递前独立授权、SecretStr 脱敏和既有配置模式均与设计一致 |

## 需求与场景核验

### Web HTTP 告警目标由部署者授权

实现：`api/services/alert_target_policy.py:16` 定义默认空列表及秘密配置，`:29` 拒绝危险 URL 语法，`:59` 执行完整字符串精确授权；`api/services/cost_service.py:620` 和 `:677` 在创建及更新最终状态时共用同一函数。更新在原有事务内校验，失败回滚所有字段。

| 场景 | 实现与测试证据 |
| --- | --- |
| 拒绝未授权网络目标 | `test_unapproved_targets_rejected_without_network` 对 Slack/Webhook 参数化覆盖 IPv4 回环、IPv6 回环/私网、私网、链路本地、可解析至私网的未授权域名；断言 400、未落库、DNS/HTTP 均零调用 |
| 精确允许公共目标 | `test_complete_url_with_query_is_allowed` 及原有 CRUD 验证完整 HTTPS URL、路径/query 大小写和增补参数不扩大授权；端口、前缀、伪装域名拒绝由参数化测试覆盖 |
| 默认拒绝和危险语法 | `test_policy_defaults_and_settings_repr_hide_secrets`、`test_empty_or_invalid_allowlist_fails_closed`、`test_dangerous_syntax_rejected_even_if_listed` 覆盖空/无效配置及 HTTPS、凭据、控制字符、反斜杠、片段、authority/端口；错误及 repr 无秘密 |
| 最终状态与事务回滚 | `test_invalid_final_target_rolls_back_all_changes`、`test_channel_only_change_cannot_authorize_log_target` 覆盖授权撤销后的名称/启用/通道修改和全部字段回滚，保留改为 log 的能力；原 masked target 回归继续通过 |

### Web HTTP 历史规则在投递边界重新授权

实现：`api/services/cost_alert_service.py:59` 在构造每条 HTTP 规则的发送配置前重新校验；异常沿原有失败与脱敏路径处理。共享 `src/cost_alert.py` 未修改，Web 仍传入 `follow_redirects=False`，requests 继续使用默认 TLS 验证和原有有界重试。

| 场景 | 实现与测试证据 |
| --- | --- |
| 历史内网规则不能发送 | `test_legacy_unapproved_target_never_reaches_transport` 直接插入历史非法目标；DNS/HTTP 零调用，失败历史正确，其他 log 规则与站内通知正常 |
| 投递时撤销授权 | `test_worker_rechecks_revoked_authorization` 在 dispatcher 创建后更改部署环境，发送前按当前配置拒绝，未沿用旧授权 |
| 合法投递与其他通道 | 既有 Web 去重、并发、恢复、Slack/SMTP、失败隔离、禁重定向测试继续通过；新增 `test_web_tls_failure_is_not_retried` 验证 TLS 错误停止重试；CLI 36 项成本告警测试通过 |

## 实际检查

所有命令 cwd 均为项目根目录。Python 测试使用 `MPLCONFIGDIR=/private/tmp/issue-509-mpl`。

1. 修复前运行 `.venv/bin/python -m pytest tests/test_web_cost_alerts.py -k 'legacy_unapproved or revoked' -q --no-cov --maxfail=1`，实际失败：HTTP mock 收到一次 `https://127.0.0.1:9443/internal`，证实回归测试能检出原缺陷。
2. 修复后运行 `.venv/bin/python -m pytest tests/test_api_cost.py tests/test_web_cost_alerts.py tests/test_cost_alert.py -q --no-cov`：146 项收集，142 passed，4 个既有真实 HTTP 测试因沙箱禁止 `listener.bind(('127.0.0.1', 0))` 发生 setup error。日志 `/private/tmp/issue-509-full-tests.log`。
3. 对上述 4 项执行获准的本地端口补跑：`.venv/bin/python -m pytest tests/test_api_cost.py -k 'full_model_ids_round_trip_over_http or full_model_id_auth_and_validation_over_http or real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery' -q --no-cov`：4 passed，79 deselected。日志 `/private/tmp/issue-509-http-tests.log`。因此同一最终代码的 146 项已全部核验通过，没有遗留测试失败。
4. `.venv/bin/ruff check api/services/alert_target_policy.py api/services/cost_service.py api/services/cost_alert_service.py tests/test_api_cost.py tests/test_web_cost_alerts.py`：All checks passed。
5. `.venv/bin/black --check` 对同一 5 个 Python 文件：5 files would be left unchanged。
6. `git diff --check`：通过。
7. `comet classic openspec -- validate restrict-web-alert-targets --strict`：Change is valid。

测试中的模型、DNS、HTTP 告警与 SMTP 均使用隔离替身；获准补跑的真实 HTTP 只绑定本地临时测试服务。没有访问真实内网或生产告警地址。

## 范围、审查与限制

- 交付文件：新增 `api/services/alert_target_policy.py`，修改两个费用 service、两个相关测试文件及 `docs/cost-alerts.md`，共 6 个；无架构扩展、依赖变更或数据库迁移。
- Runtime 采用本次 tweak 的 `direct/direct/off` 预设；独立 reviewer 按已选配置不适用，主会话已按 OpenSpec verify 方法检查最终 diff、需求、设计和全部场景。
- 文档说明 API/worker 使用相同 `COST_ALERT_ALLOWED_WEBHOOK_URLS` JSON 数组并重启；默认空列表会拒绝已有 Web HTTP 告警。
- 采用已批准的部署白名单边界：完整目标及其 DNS 由部署者信任，不能配置普通用户控制的域名。本次不实现任意公共地址访问，也不提供对部署者错误授权或可信 DNS 被接管的保证。
- 没有运行仓库全量测试、生产环境或真实外部网络验收；与本次修改相关的费用 API、Web 告警与 CLI 告警均已覆盖。现有 Pydantic/pytest-asyncio/datetime 弃用提示与本次修改无关。
