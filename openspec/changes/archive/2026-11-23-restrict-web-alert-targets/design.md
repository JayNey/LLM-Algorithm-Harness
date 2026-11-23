# Web 告警目标白名单设计

## Context

问题及隔离复现见 proposal.md。`CostService.create_rule/update_rule` 接受普通用户目标；`WebCostAlertDispatcher` 从数据库构造配置并交给共享发送器。共享发送器还用于部署者可信的 CLI 配置。本次保留现有调用结构和 SMTP 配置。

## Goals / Non-Goals

目标是让部署者掌握 Web HTTP 告警目的地的授权，覆盖写入和历史投递。具体验收以 `specs/api/cost-management/spec.md` 为准。不引入新 API、数据库迁移或通用网络传输框架。

## Decisions

1. 新增 `api/services/alert_target_policy.py`，使用与现有 Web SMTP 设置一致的 BaseSettings 环境加载方式，读取 `COST_ALERT_ALLOWED_WEBHOOK_URLS`（完整 HTTPS URL 的 JSON 数组，默认 `[]`）。API 与 worker 共用函数，每次相关操作读取有效配置。配置值包含秘密路径或 query 时应使用 SecretStr，错误只返回固定脱敏消息。
2. 完整 URL 做精确匹配，不支持通配符、后缀、前缀或任意路径；拒绝非 HTTPS、内嵌凭据、片段、反斜杠、控制字符或无效 authority/端口等歧义。保留完整路径和 query 的大小写及含义。精确匹配成功后使用部署配置中的目标值，避免产生用户可选的新地址。
3. 创建前检查；更新在同一数据库事务内检查修改后的完整规则（包括仅更换 channel、启用、阈值等情况），拒绝时回滚全部字段。log/SMTP 维持原有必填与目标行为。
4. worker 在每次规则投递前重新校验，包括升级前直接写入的历史记录。白名单撤销后不能沿用创建时的授权。拒绝目标沿现有失败路径记录脱敏失败历史，保持站内预警和评估继续执行。HTTP 重试只使用同次授权的部署者固定 URL；继续通过共享发送器禁重定向并使用默认 TLS 校验。
5. 选择 issue 明确允许的部署白名单方案。替代方案是允许任意公共地址并将 DNS 校验结果绑定实际 TLS 连接；仅提前解析 DNS 再调用 requests 会留下二次解析窗口。前者增加自定义连接、安全代理和 TLS/SNI 管理，本次无需引入。白名单仅能配置部署者掌控或可信服务商目标，其 DNS 控制权属于部署信任边界；不能将不可信用户域名放入白名单。

## Risks / Trade-offs

- 默认拒绝导致已有 Web HTTP 告警失败 → 部署前配置相同的 API/worker 白名单，文档说明重启与失败行为。
- 完整 URL 中可能有凭据 → 不写入日志、错误、配置 repr 或 HTTP 响应，不枚举允许目标。
- API/worker 配置不一致 → 两端执行相同策略，worker 始终独立拒绝；文档要求同步部署。
- 部署者将不可信域名加入白名单会破坏信任边界 → 文档明确允许列表只维护可信固定外部目标；本方案不声称提供对部署者配置错误或可信 DNS 被接管的保护。

安全方案参考：[OWASP SSRF Prevention — trusted destination allowlist](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html#case-1-application-can-send-request-only-to-identified-and-trusted-applications)。

## Migration Plan

部署者在 API 与 worker 环境中填写相同 JSON 数组并重启。未授权的历史规则仍可列出和删除，但写入时须改为合法最终状态，投递会记录失败。SMTP/log 和 CLI 不受该白名单影响。回滚代码会重新开放旧边界，应保留修复并调整部署配置。

## Validation

在 `tests/test_api_cost.py` 覆盖创建/更新拒绝、事务回滚、默认空配置、精确匹配和合法目标。`tests/test_web_cost_alerts.py` 覆盖历史内网目标、IPv4/IPv6/私网/未授权域名拒绝、授权撤销、Slack 与 Webhook、TLS/重定向和其他渠道回归。未授权域名包括测试中模拟解析至私网的域名，必须在调用解析/HTTP 前拒绝。所有 HTTP、DNS 和 SMTP 行为使用替身；不访问真实内网或外部服务。运行相关 pytest、Ruff/格式检查及 OpenSpec 严格校验。
