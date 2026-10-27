# Web 预警通知验证

结论：PASS。change 为 web-cost-alert-notifications；分支 comet/web-cost-alert-notifications，基线 c42f9d1。完整验证（tweak 不要求 Superpowers Design Doc/plan，按 design.md 对照）。3/3 任务完成，既有 api/cost-management 的预警能力 delta 全部覆盖。

## 验证证据

- 最终相关回归：`MPLCONFIGDIR=/tmp/harness-mpl pytest tests/test_web_cost_alerts.py tests/test_api_cost.py tests/test_cost_alert.py tests/test_celery_tasks.py tests/test_evaluation_async_flow.py tests/test_async_task_integration.py -q -o addopts=''`：143 passed、2 skipped，5 条既有 Pydantic 弃用警告。
- 全仓 `pytest`：3282 passed、11 skipped、1 failed、14 errors；覆盖率 92.21%，超过 90%。该轮在修改过程中启动，收集了更新前的预算快照测试；对应断言已同步新增金额字段，最终相关回归已通过。14 项 Nginx errors 均为沙箱禁止绑定回环端口；在获准监听的环境重跑 `pytest tests/test_deployment_readiness.py -q -o addopts=''`：14 passed。此处不将初始整套命令表述为全绿。
- `python3 -m compileall -q src/cost_alert.py api/services/cost_alert_service.py api/services/cost_service.py src/tasks/evaluation.py`：成功。
- 修改的 7 个 Python 源码/测试文件 ruff check、format --check 均通过；`git diff --check` 通过。
- `comet classic openspec -- validate web-cost-alert-notifications --strict`：通过。

## 完整性与正确性

- 规则 CRUD、非法规则、目标脱敏：既有 API tests；历史过滤 pending，仅返回 owner 成功通知。
- HTTP 保存规则→真实 TaskService worker→100% 通知→历史：暂停和降级两种路径均通过。
- Slack JSON、Webhook payload、SMTP 邮件目标、100% 精度、失败有界重试及脱敏、禁用/其他用户/低于阈值/无上限：Web dispatcher tests 通过。
- 持久恢复去重、两个并发 worker、未知用量不虚增已知成本、预算变化重新触发、禁用动态读取：均通过。
- 慢发送不锁住评估成本提交；Web 重定向失败；在途租约隐藏与过期恢复：均通过。

## 代码审查闭环

使用 requesting-code-review 技能执行独立只读集成审查。两项 P1 已修复并经同一审查者核查：网络投递移出数据库事务；Web 禁止重定向且拒绝 3xx。无未解决 CRITICAL/IMPORTANT。默认 review_mode=off 原因是 tweak 预设；本次额外完成独立人工式 agent 审查。

## 设计一致性与限制

复用既有传输且保留 CLI 行为，不引入数据库迁移或新 HTTP API。用户已确认跨模块范围继续 tweak。设计与 delta 无矛盾，改动范围与 tasks 一致。

通知按个人全局预算、持久化已知累计成本判断，在 Web 评估边界触发；不进行后台轮询。SMTP 需要 worker 环境配置。真实外部 Slack/邮件/Webhook 使用受控传输替身验证，未向用户真实收件目标发送；PostgreSQL 实机并发未验证，SQLite 并发已验证。5 分钟投递租约在进程中断后需后续边界回收；租期超时或远端成功到本地提交的窗口可能重复，接收方应按规则/阈值/上限去重。这些是已记录的交付语义，无新增偏差。

## 初始全仓失败项及解决证据

以下快照失败已在最终相关回归通过；以下 Nginx 项已在获准监听的环境全部通过：

```text
FAILED tests/test_celery_tasks.py::TestPersonalBudgetExecution::test_execution_snapshot_uses_actual_difficulty_and_owner
ERROR tests/test_deployment_readiness.py::test_nginx_runtime_pid_is_isolated
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/evaluations]
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/auth/login]
ERROR tests/test_deployment_readiness.py::test_unready_blocks_business_and_recovers[/api/v1/ws/progress]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[401]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[403]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[500]
ERROR tests/test_deployment_readiness.py::test_probe_error_and_timeout_fail_closed[timeout]
ERROR tests/test_deployment_readiness.py::test_probe_is_get_without_client_credentials_body_or_query
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[401]
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[403]
ERROR tests/test_deployment_readiness.py::test_business_errors_are_preserved[500]
ERROR tests/test_deployment_readiness.py::test_probe_requests_do_not_hit_business_rate_limit
ERROR tests/test_deployment_readiness.py::test_websocket_upgrade_headers_survive_admission
= 1 failed, 3282 passed, 11 skipped, 127 warnings, 14 errors in 417.94s (0:06:57) =
```
