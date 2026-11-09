## MODIFIED Requirements

### Requirement: 本地开发服务器

前端工程 SHALL 能启动本地开发服务器，源码变更后热更新，并在 `http://localhost:3000` 和 `http://127.0.0.1:3000` 提供本地入口。开发服务器 SHALL 将以 `/api` 开头的 HTTP 请求和 WebSocket 升级转发到配置的后端 origin。

#### Scenario: 开发服务器转发 API

- **WHEN** 开发服务器正在运行且客户端请求 `/api/v1/health`
- **THEN** 该请求被转发到后端 origin，而不是由前端静态资源处理

#### Scenario: 默认开发入口使用同源会话

- **WHEN** 用户按文档启动本地服务，在任一支持的主机名上登录并调用受保护 API
- **THEN** 登录和受保护 API 请求经页面同源的 `/api` 代理到达后端，无需额外配置后端允许的跨源来源
- **AND** 浏览器通过当前页面主机连接 `/api/v1/ws/progress` 时，代理将升级请求及会话 Cookie 交给同一个后端，后端返回已认证的连接帧

### Requirement: 环境配置

前端 SHALL 按开发、测试和生产模式读取 API Base URL、WebSocket URL、应用名称和功能开关。必填地址缺失时 SHALL 失败并指出变量名，不得静默使用空地址。

#### Scenario: 开发模式读取地址

- **WHEN** 以开发模式启动应用
- **THEN** 应用读到该模式配置的 API Base URL、WebSocket URL 和应用名称
- **AND** 默认 API Base URL 为 `/api/v1`，默认 WebSocket 路径为 `/api/v1/ws/progress`，两者均基于页面当前主机解析

#### Scenario: 缺少 API 地址

- **WHEN** 当前模式没有提供 API Base URL
- **THEN** 启动或构建失败，并指出缺失的变量名
