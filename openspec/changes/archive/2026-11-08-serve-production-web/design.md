## Context

生产 Compose 已将 Nginx 设为唯一公开入口。Vite 的生产配置已使用相对 API 与 WebSocket 路径，同源发布可直接使用现有 Cookie 鉴权。

## Decisions

- 生产 Nginx 镜像通过多阶段构建打包 `frontend/dist` 和代理配置。构建上下文只纳入前端输入及代理配置，隔离本地依赖和环境覆盖。
- Nginx 将业务 API 与框架文档路由转发给 API。健康和系统诊断路径沿用现有豁免。SPA 和静态资源独立提供，入口 HTML 使用重新验证缓存策略，缺失的路由分包返回 404。
- 使用 Compose 内置 DNS 更新 API 地址，使 API 容器重建后无需重启 Nginx。就绪检查继续控制业务 API 与 WebSocket 握手。
- 发布时重建 Nginx 镜像。HTTPS 部署从同一配置启用证书与端口。验收在隔离的生产 Compose 实例执行，记录页面、会话 Cookie、WebSocket 与故障恢复结果。
- 镜像内的 `npm ci` 需要锁定 `package.json` 已声明的国际化依赖。用户确认同步锁文件后继续使用 tweak，变更范围仍为生产 Web 发布与验收。
