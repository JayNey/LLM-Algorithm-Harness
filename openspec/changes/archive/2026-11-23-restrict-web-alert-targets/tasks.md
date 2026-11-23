# 实施与验收任务

## 1. 统一目标授权与规则写入

- [x] 1.1 在 `api/services/alert_target_policy.py` 实现部署白名单与严格完整 HTTPS URL 校验，并在 `tests/test_api_cost.py` 覆盖默认拒绝、精确允许、危险语法、回环/IPv6/私网和未授权域名；验证拒绝时未调用网络且错误脱敏。
- [x] 1.2 将同一策略接入 `CostService.create_rule/update_rule`，在 `tests/test_api_cost.py` 验证合法 CRUD、最终状态校验、授权撤销、仅变更通道及拒绝后的事务回滚；保留原有目标脱敏和 masked target 回归。
- [x] 1.3 更新 `docs/cost-alerts.md`，提供白名单 JSON 配置、可信域名/DNS 边界、API/worker 同步重启和历史规则影响；核对示例与实际设置字段一致且不包含真实凭据。

## 2. 历史规则投递边界

- [x] 2.1 将相同策略接入 `WebCostAlertDispatcher` 的发送前边界，在 `tests/test_web_cost_alerts.py` 验证历史非法目标和已撤销目标不进入 HTTP 层，包含解析至私网的未授权域名，并保持失败历史及站内通知独立。
- [x] 2.2 更新上述两个测试文件的合法部署配置，验证允许公共目标的 Slack/Webhook 投递、禁重定向、TLS 错误、有界重试/恢复去重及 SMTP/log 回归；所有 DNS/HTTP/SMTP 使用隔离替身。

## 3. 集成验收

- [x] 3.1 运行相关 API、Web 预警和 CLI 成本告警测试及 Ruff/格式检查，对照 delta spec 逐项核验；执行 `comet classic openspec -- validate restrict-web-alert-targets --strict` 并记录实际结果与未执行项。

## Workflow follow-up

- Verify 通过后按 Comet Archive 流程取得当前交付授权，再归档和执行选定的 Git 交付。
