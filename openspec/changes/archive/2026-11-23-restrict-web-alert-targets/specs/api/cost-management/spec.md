## ADDED Requirements

### Requirement: Web HTTP 告警目标由部署者授权

Web Slack 与 Webhook 规则的目标 SHALL 只允许部署者配置的完整 HTTPS URL。系统 SHALL 精确匹配完整目标，不使用通配符、域名后缀或 URL 前缀授权。默认空白名单 SHALL 拒绝 Web HTTP 告警。创建和更新规则 SHALL 对最终状态执行相同策略，不合法时返回 400 且不持久化任何本次字段修改。错误和响应 SHALL 不泄露目标凭据或白名单内容。SMTP、log 和部署者本地 CLI 目标 SHALL 保持既有配置行为。

#### Scenario: 拒绝未授权网络目标

- **WHEN** 普通用户创建 Slack/Webhook 规则，目标是白名单之外的回环 IPv4、IPv6、私网、链路本地地址，或解析至私网的域名
- **THEN** 返回 400，不创建规则、不发出 DNS 查询或 HTTP 请求，错误不包含目标秘密

#### Scenario: 精确允许公共目标

- **WHEN** 部署者配置可信公共 HTTPS 完整目标，普通用户使用相同完整 URL 创建规则
- **THEN** 创建成功，响应继续脱敏；相同主机上的其他路径、端口、query、伪装后缀或 URL 前缀不因该配置获准

#### Scenario: 默认拒绝和危险 URL 语法

- **WHEN** 白名单为空或无效，或目标含非 HTTPS、内嵌凭据、片段或有歧义的 authority/控制字符
- **THEN** 创建和更新均被拒绝，不枚举配置内容或泄露目标

#### Scenario: 更新最终状态与事务回滚

- **WHEN** 更新目标或通道后最终 HTTP 目标未获准，或只更新启用状态、名称、阈值时原目标已经撤销授权
- **THEN** 返回 400，所有本次变更回滚；合法的 SMTP/log 最终状态仍按原规则处理

### Requirement: Web HTTP 历史规则在投递边界重新授权

Worker SHALL 在投递每条 Web Slack/Webhook 规则前按当前部署配置重新校验完整目标，包括升级前保存的规则。未获授权的目标 SHALL 不进入 HTTP 发送层；失败 SHALL 脱敏记录并保持评估、预算动作及站内预警继续工作。获准 HTTP 投递 SHALL 保留 TLS 证书验证、禁重定向、有界重试与成功去重。白名单目标及 DNS 控制权 SHALL 属于可信部署配置，而非普通用户输入。

#### Scenario: 历史内网规则不能发送

- **WHEN** 数据库已有回环、IPv6、私网或未授权域名规则，且用户已知成本达到阈值
- **THEN** Worker 不向该目标发出请求，历史记录失败且无凭据，其他合法规则和站内通知继续工作

#### Scenario: 授权撤销在投递时生效

- **WHEN** 规则创建后目标从部署配置移除，并以更新后的配置启动 Worker 投递或恢复
- **THEN** 不沿用创建时授权，拒绝发送该规则

#### Scenario: 合法投递与其他通道兼容

- **WHEN** 目标仍精确位于部署白名单，或投递 SMTP/log 规则
- **THEN** 合法 HTTP 目标按既有 TLS 和禁重定向方式发送并保留去重、失败隔离及有界重试；其他通道维持现有行为
