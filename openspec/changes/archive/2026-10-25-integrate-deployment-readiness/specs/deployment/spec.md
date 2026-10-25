## MODIFIED Requirements

### Requirement: 反向代理

系统 SHALL 提供 nginx 配置：将请求反代至 api 服务，启用 gzip，对 API 路径按来源限流，为 `/api/v1/ws` 提供 WebSocket 升级代理，并 SHALL 给出 HTTPS 启用的注释模板；请求体上限 SHALL 与上传服务的上限对齐。业务请求及 WebSocket 握手 SHALL 在就绪接口 `/api/v1/health/ready` 成功后才准入；就绪失败、异常或超时 SHALL 返回 503。存活探针 SHALL 继续使用 `/api/v1/health`；健康接口与管理员诊断 SHALL 不受就绪准入或业务限流阻断。业务可用性告警 SHALL 以就绪接口 HTTP 200 为成功条件，而非存活或管理员诊断响应。

#### Scenario: WebSocket 经代理升级
- **WHEN** API 就绪且客户端经 nginx 对 `/api/v1/ws` 发起 WebSocket 升级请求
- **THEN** nginx 附加 Upgrade 与 Connection 头将连接代理至 api，连接保持长连

#### Scenario: 超限请求被限流
- **WHEN** 同一来源在限流窗口内对业务 API 路径发起超过阈值的请求
- **THEN** 超出部分收到限流错误响应，服务后端不被直接打穿

#### Scenario: 未就绪关闭业务准入
- **WHEN** 就绪接口返回 503、不可达或超时
- **THEN** nginx 不转发业务请求与新 WebSocket 握手，返回 503，存活与诊断路径仍可访问

#### Scenario: 恢复准入
- **WHEN** 就绪接口重新返回 200
- **THEN** 后续业务请求可通过准入，应用自身错误状态保持原样

#### Scenario: 可用性监控
- **WHEN** 就绪接口失败或超时且存活接口仍为 200
- **THEN** 业务可用性监控判定失败，存活监控继续成功，告警示例覆盖此情形
