# 生产 Web 发布验证

`serve-production-web` 已完成 2/2 项实现任务，提交为 `66dcfe05` 和 `eca3b6bd`。生产 Compose 由 Nginx 镜像提供 SPA，同一发布地址提供 API 和进度 WebSocket。

## 发布入口验收

使用仓库的生产 Compose 构建镜像和启动六项服务。隔离验收实例使用本地回环端口、独立卷和临时账号。另用同一 Nginx 镜像和临时证书验收 HTTPS。验收地址为 `http://127.0.0.1:18398` 和 `https://127.0.0.1:18498`。

- Chromium 访问 `/login`，HTML 和登录分包均返回 200。禁用缓存后硬刷新 `/experiments/new`，HTML 和业务路由分包均返回 200。入口 HTML 带 `Cache-Control: no-cache`，缺失分包和未知 API 路径各自返回 404，OpenAPI 文档返回 200。
- 浏览器登录返回 200。Access 与 refresh Cookie 为 HttpOnly、SameSite=Lax，并分别限定到 `/api` 和 `/api/v1/auth`。浏览器携带会话调用 `/api/v1/users/me` 成功，WebSocket 收到 `connected` 和 `pong`。HTTPS 实例另验证了 `Secure` Cookie 和 `wss://`。
- 停止 PostgreSQL 后，API 存活探针保持 200，就绪探针返回 503，登录页与业务深链接保持 200，业务请求和新 WebSocket 握手返回 503。重新启动数据库后，已有浏览器会话可正常访问 API 和建立 WebSocket。停止并重建 API 容器后，Nginx 保持运行，页面持续可访问，API 和 WebSocket 随就绪恢复。

## 规格与设计核对

`deployment` 增量规格的三个场景均有真实 Compose 或浏览器证据。多阶段镜像仅携带 Nginx 配置和前端构建产物。SPA 路由和 API/WS 准入分开，API 地址通过 Compose 内置 DNS 更新。部署说明覆盖构建输入、发布更新、HTTPS 和验收步骤。Tweak 使用变更内的精简设计，`review_mode: off`，已按基线差异和规格逐项复核。

## 自动检查与验收边界

- 生产 Compose 配置检查、镜像构建、六项服务健康检查和容器内 `nginx -t` 均通过。
- 部署配置、Nginx 代理和 API 就绪共 85 项 Python 测试通过。使用锁文件干净安装后，前端 322 项测试通过。修改文件通过 Ruff、Prettier 检查和 `git diff --check`。OpenSpec 通过严格校验。
- 全量 Python 测试通过 4062 项，跳过 18 项，覆盖率 93.44%。宿主安装的 Anthropic SDK 1.5.0 使用 `httpx2`，导致 4 项策略用例在初始化时出错。使用符合项目 `<1` 约束的 0.125.0 在独立目录重跑该测试文件，12 项全部通过。
- 生产构建的 npm 审计与基线均报告相同的 14 项告警，包括 Monaco 间接依赖 DOMPurify 的 Critical 告警。全仓前端格式检查仍报告基线文件 `frontend/scripts/verify-settings.mjs`。
- 验收使用生产编排的本地发布地址。公网域名、公开证书和外部网络链路需在正式部署后验收。
