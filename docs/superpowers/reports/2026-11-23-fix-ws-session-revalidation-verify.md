# 验证报告：fix-ws-session-revalidation

## 范围与配置

针对 GitHub #510 修复进度 WebSocket 的连接生命周期鉴权。业务差异仅包含 `api/routes/ws.py` 与 `tests/test_api_ws.py`，无需数据库迁移或外部服务协议调整。当前 Run 使用 tweak、direct/direct/off；独立审查按已选预设关闭，由当前会话完成最终差异核对。

用户已确认沿用 `api/password-change` 的现有行为：修改密码后当前会话继续有效，后续注销才触发连接关闭。设计中的相反假设已纠正，并通过原 Run 的范围澄清记录保留该决定。

## 完整性、正确性与一致性

| 维度 | 验证结果 |
| --- | --- |
| 完整性 | tasks.md 的 3/3 任务完成；1 个 MODIFIED requirement 已实现 |
| 正确性 | WebSocket 订阅与鉴权的 9 个场景均有实现与测试映射 |
| 一致性 | 复用原始建连凭据和现有认证服务；每秒检查；锁保护发送和关闭；统一取消、等待与订阅清理；符合已确认设计 |

## 规格与测试映射

| 场景 | 实现依据 | 验证依据（tests/test_api_ws.py） |
| --- | --- | --- |
| 仅任务所有者可订阅 | ws.py:115 的用户归属查询及 4403 关闭 | test_cross_user_subscription_is_denied_4403 |
| 订阅即得快照 | ws.py:110 先订阅、122 发送快照与确认，再启动转发 | test_subscribe_sends_snapshot_and_forwards_events；test_execution_progress_snapshot_matches_http_and_preserves_worker_event |
| 无效令牌被拒 | ws.py:35 的初始认证与 4401 | TestAuthentication 中无效、缺失和 Cookie 入口测试 |
| 注销后旧连接发起订阅 | ws.py:138 动作前认证；重复订阅也使用鉴权发送包装 | test_logout_blocks_new_and_duplicate_subscriptions，query/cookie × fresh/duplicate |
| 注销后既有订阅收到事件 | ws.py:61、82 发送前重新认证且统一关闭 | test_logout_blocks_events_on_existing_subscriptions |
| 密码变更保留现有会话 | 复用认证服务，按现有密码规范保持有效 | test_password_change_keeps_connection_until_logout；test_api_auth.py 的改密保留会话测试 |
| 访问令牌到期 | 原始 JWT 每次由认证服务解码，不仅检查缓存 principal | test_access_token_expiry_closes_connection，idle/event/subscribe/ping 四种路径；确认底层会话仍存在但 HTTP 已拒绝 |
| 空闲连接检查失效凭据 | ws.py:72 的独立定期检查与连接监督 | test_idle_connection_closes_after_logout，含有/无订阅；test_revocation_from_another_auth_service_closes_connection |
| Cookie 认证连接遵守会话失效 | ws.py:33 固定保存实际 Cookie 凭据并复用 | test_logout_blocks_new_and_duplicate_subscriptions 的 cookie 参数 |

额外覆盖订阅建立期间撤销、快照读取期间撤销、异步清理竞争，以及正常断连/注销时释放两项订阅。先以 `None` 转发任务登记半初始化订阅，关闭后仍由同一 finally 回收；ASGI 取消期间使用受保护的清理过程，未完成清理的条目仍保留在登记表中。

## 实际检查

所有命令工作目录为 `/Users/verstappen/LLM-Algorithm-Harness`。

- 最终候选：`.venv/bin/python -m pytest tests/test_api_ws.py -q --no-cov`：**28 passed**，5 项现有弃用警告，43.65 秒；日志 `/tmp/issue-510-ws-final.log`。
- 相关集成回归：`.venv/bin/python -m pytest tests/test_api_ws.py tests/test_api_auth.py tests/test_task_submission_authorization.py tests/integration/test_api_workflows.py -q --no-cov`：**142 passed**，35 项警告，80.37 秒；日志 `/tmp/issue-510-regression.log`。之后仅修改 WebSocket 的半初始化订阅登记并追加测试，最终 28 项已覆盖这些改动；其余认证、权限与离线 API 工作流结果仍适用。
- `.venv/bin/python -m ruff check api/routes/ws.py tests/test_api_ws.py`：通过。
- `.venv/bin/python -m black --check api/routes/ws.py tests/test_api_ws.py`：通过。
- `git diff --check`：通过。
- `comet classic openspec -- validate fix-ws-session-revalidation --strict`：通过。

## 缺陷复现与修复证据

- 修改生产代码前，新增的 14 项生命周期回归全部失败：旧连接泄漏快照、订阅确认和事件，或在失效后保持连接。日志 `/tmp/issue-510-red.log`。
- 首轮修改后，原有正常断连测试暴露 ASGI 取消打断异步清理的问题；增加受保护清理后，全部 24 项当时的 WebSocket 测试通过。历史日志 `/tmp/issue-510-green.log`。
- 针对半初始化订阅，新增 `test_revocation_during_subscription_releases_with_async_cleanup` 先确认失败：连接关闭后订阅仍未释放。日志 `/tmp/issue-510-cleanup-red.log`。订阅建立后立即登记并统一清理后，此测试及最终 28 项全部通过。

## 验证边界与待补结果

相关回归使用真实路由、认证、JWT 校验和临时 SQLite；进度传输为内存替身，到期与并发边界使用可控时间及同步点。未进行真实付费模型调用、生产故障注入或真实 Redis 进度链路验证。定期认证的检测周期为一秒；与任意认证后发送相同，认证完成与网络发送之间仍存在极短时间窗口。

额外离线全套命令 `.venv/bin/python -m pytest -q --no-cov -m 'not online' --maxfail=5` 收集 4465 项，在约 15% 时已出现 4 项 setup error，主动以 SIGINT 中止用于诊断；没有完整的全套通过结论。日志 `/tmp/issue-510-suite.log`。中止时 pytest 的 tmp_path 清理另报 StashKey KeyError，记录为中止过程异常，不作为业务回归通过依据。

4 项错误均在 `tests/test_api_cost.py:631` 的 `listener.bind(("127.0.0.1", 0))` 抛出 `PermissionError: [Errno 1] Operation not permitted`，尚未进入业务断言。单独在同一沙箱复现得到 4 errors，日志 `/tmp/issue-510-suite-errors.log`：

- `TestPricing::test_full_model_ids_round_trip_over_http`
- `TestPricing::test_full_model_id_auth_and_validation_over_http`
- `test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]`
- `test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[ab]`

允许本地回环测试服务后，对上述 4 项原样重验得到 **4 passed**（9 项弃用警告，5.64 秒），日志 `/tmp/issue-510-suite-errors-recheck.log`。命令为 `.venv/bin/python -m pytest tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http tests/test_api_cost.py::TestPricing::test_full_model_id_auth_and_validation_over_http tests/test_api_cost.py::test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery -q --no-cov`。模型响应为测试替身。

## 结论

本次范围内的任务、1 项需求及全部 9 个场景已核对，未发现未解决的 CRITICAL、IMPORTANT、WARNING 或 SUGGESTION。必要回归与格式、规格检查均通过，可进入归档交付决定。仓库额外全套验证不完整，不能声称仓库全量测试通过。独立审查按本 Run 的 review_mode=off 不执行。
