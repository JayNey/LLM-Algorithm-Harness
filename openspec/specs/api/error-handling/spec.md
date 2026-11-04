# api/error-handling Specification

## Purpose
定义 HTTP API 的统一错误响应、稳定错误码、请求关联标识、敏感信息保护及客户端兼容语义，确保异常处理和中间件提前拒绝遵循同一契约。

## Requirements

### Requirement: 统一 HTTP 错误响应

系统 SHALL 为尚未开始发送响应的 HTTP 4xx/5xx 错误提供 success=false 和 error 对象，包含稳定大写 code、可读 message、结构化 details 和非空 request_id。系统 SHALL 保留现有客户端使用的顶层 message/detail/details 兼容字段；成功响应与 WebSocket 协议不变。

#### Scenario: 参数校验失败

- **WHEN** 请求参数不合法
- **THEN** 返回 HTTP 400、INVALID_PARAMETER、字段级 details，且顶层兼容 details 与规范 details 一致，不回显请求原始输入

#### Scenario: HTTP 与业务异常

- **WHEN** 路由或框架返回 HTTP 错误，或调用点显式抛出已定义业务码的 ApiError
- **THEN** 分别按 HTTP 状态映射或显式业务码返回规范对象，框架 404/405 也使用该对象，不能根据英文错误文案猜测业务码

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

### Requirement: 请求关联和内部错误保护

系统 SHALL 使用服务端生成的请求 ID，error.request_id 和 X-Request-ID 一致，不直接采用不可信客户端输入。内部异常 SHALL 返回通用消息，响应与错误日志不得记录原始异常中的凭证。

#### Scenario: 未处理异常

- **WHEN** 请求执行产生未处理异常，异常字符串包含私密数据
- **THEN** 返回 500/INTERNAL_ERROR，响应和应用错误日志均不包含私密数据，响应 ID 与日志 ID 可关联

#### Scenario: 并发请求与外部 ID

- **WHEN** 多个请求携带相同或恶意 X-Request-ID
- **THEN** 各请求使用独立服务端 ID，同一请求响应头与错误体 ID 一致

### Requirement: 错误契约可发现

系统 SHALL 在 OpenAPI 中公开错误模型与错误码，并提供兼容字段、默认映射和显式业务码使用说明。

#### Scenario: 查看规范

- **WHEN** 客户端读取 OpenAPI 和开发文档
- **THEN** 可定位规范错误结构和错误码枚举，参数校验错误文档与实际 HTTP 400 一致
