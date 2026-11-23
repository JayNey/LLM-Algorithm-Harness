# 限制 Web 成本告警投递目标

## Why

Issue [#509](https://github.com/JayNey/LLM-Algorithm-Harness/issues/509) 指出普通用户可以将 Web 告警指向 worker 内网。已在当前基线通过替换 HTTP 发送层复现：`https://127.0.0.1:9443/internal` 通过配置校验并进入发送层，即使禁用重定向仍返回发送成功；复现未访问真实网络。

## What Changes

- 为 Web Slack/Webhook 引入部署者维护的完整 HTTPS URL 白名单，普通用户不能通过接口扩展白名单。
- 创建规则、修改规则的最终状态、worker 投递历史规则统一执行同一校验；拒绝目标不发出请求。
- **BREAKING**：默认空白名单拒绝 Web HTTP 告警；现有部署必须在 API 和 worker 配置相同的允许目标并重启，历史规则在投递时也受限制。
- 保留 HTTPS、TLS 证书验证、禁重定向、脱敏、失败隔离和既有有界重试行为。
- 增加目标限制回归测试及部署说明。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `api/cost-management`：增加 Web HTTP 告警的部署授权目标限制，覆盖创建、更新和历史规则投递。

## Impact

预计修改 6 个交付文件：新增共享目标策略模块，修改 `api/services/cost_service.py`、`api/services/cost_alert_service.py`、`tests/test_api_cost.py`、`tests/test_web_cost_alerts.py` 和 `docs/cost-alerts.md`。不增加数据库字段、依赖或 API 端点。CLI 仍使用部署者本地配置；SMTP/log 的目标策略不变。

采用 issue 允许的部署白名单方案：完整目标的选择权归部署者；白名单域名及其 DNS 控制权属于可信部署边界，不接受用户提供任意域名再仅作保存时 DNS 检查。白名单配置应仅包含部署者掌控或可信服务商的固定外部目标，不能配置用户可控域名。
