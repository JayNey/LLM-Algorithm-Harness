## MODIFIED Requirements

### Requirement: 认证和边界错误一致

系统 SHALL 将认证和上传中间件提前拒绝纳入统一契约，保留原状态码及 WWW-Authenticate、Retry-After、Cache-Control 等有效头，不破坏 CORS 和上传清理。refresh 的 CSRF JSON 预读 MUST 逐块执行 16KiB 累计上限，并在整次预读 10 秒内结束；超限或超时后 MUST NOT 继续接收或进入下游，断连 MUST 直接结束。

#### Scenario: 凭证与令牌失败

- **WHEN** 缺少凭证、登录凭证不正确或提供无效令牌
- **THEN** 前两者返回 UNAUTHORIZED，无效令牌返回 INVALID_TOKEN，均保留 401 和 WWW-Authenticate

#### Scenario: 限流与上传边界

- **WHEN** 上传容量/速率超限、请求体过大、长度非法或上传超时
- **THEN** 返回统一错误对象及对应码，并保留 429 的 Retry-After、413/408 等原状态和资源清理行为

#### Scenario: CORS 预检拒绝

- **WHEN** CORS 因来源或方法不允许而拒绝预检
- **THEN** 返回规范 HTTP 400 JSON，保留上游 CORS 策略头，不增加未经允许的来源或方法

#### Scenario: refresh 预读提前拒绝

- **WHEN** 无 Authorization、携带伪造 refresh cookie 的请求体分块累计超过 16KiB，无论是否提供 CSRF 头
- **THEN** 超限块到达后立即返回 413/PAYLOAD_TOO_LARGE，不缓存完整超限 body，不消费后续分块，响应保留 no-store 和 CORS

#### Scenario: refresh 预读超时或断连

- **WHEN** refresh 预读遇到慢请求、持续未结束分块或断连
- **THEN** 10 秒总时限内未完成则返回 408/REQUEST_TIMEOUT；断连直接结束，不进入下游

#### Scenario: 合规刷新语义

- **WHEN** refresh 请求体未超限且完整到达
- **THEN** 显式 JSON refresh_token 优先于 cookie；cookie 刷新仍要求匹配 CSRF，缺少或不匹配返回 403
