## Why

生产 Nginx 将登录页和业务深链接转发到 API，浏览器收到 JSON 404。#398 要求为生产编排确定可部署的 Web 入口并验收登录和服务恢复。

## What Changes

- 在生产 Nginx 镜像中构建并携带 Vite 产物。同一入口提供 SPA、API 和进度 WebSocket。
- 页面导航支持深链接回退，静态资源缺失返回 404。API 及 WebSocket 握手继续受现有业务就绪检查保护。
- 部署文档记录构建、HTTPS 与配置方式，并记录生产入口的验收步骤。

## Capabilities

### New Capabilities

### Modified Capabilities

- `deployment` 增加生产 Web 入口、SPA 回退和同源验收要求。

## Impact

影响生产镜像构建、Compose、Nginx 和部署文档。
