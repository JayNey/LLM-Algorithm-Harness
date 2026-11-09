## Context

Vite 已为 `/api` 配置 HTTP 转发和 WebSocket 升级。现有 HTTP 客户端支持相对 API 根路径，进度观察器会用页面协议和主机解析相对 WebSocket 路径。

## Decisions

- 开发模式使用 `/api/v1` 和 `/api/v1/ws/progress`。登录和进度连接因此共享当前页面的主机及会话 Cookie。
- Vite 与文档中的 FastAPI 启动命令均使用 IPv4 回环地址。代理显式连接 `127.0.0.1:8000`，避免后端连接取决于 `localhost` 的地址解析顺序。浏览器可通过 `localhost:3000` 或 `127.0.0.1:3000` 访问。
- Vite 固定使用端口 3000。端口被占用时给出启动错误，便于按文档排查。

## Verification

用两个独立浏览器会话验证登录、带 Cookie 的用户信息请求和进度 WebSocket。额外检查直接访问 API 的跨源预检及三种模式配置。
