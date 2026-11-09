## Why

开发模式默认使用直连 API 的绝对地址，绕过 Vite 的 `/api` 代理。通过 `127.0.0.1:3000` 登录会触发跨源预检失败，进度 WebSocket 也没有沿用页面的主机名和会话。

## What Changes

- 让默认开发 HTTP 请求和进度 WebSocket 连接经页面同源的 `/api` 代理转发。
- 统一前端 README 中 API 和 Vite 的启动命令、支持的主机名和代理目标。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `frontend/app-shell` 的默认开发环境地址以及本地 HTTP 和 WebSocket 转发约定。

## Impact

涉及前端开发环境文件、Vite 开发服务器配置和前端 README。沿用现有后端 CORS 及生产和测试模式配置。

关联 [#432](https://github.com/JayNey/LLM-Algorithm-Harness/issues/432)。
