# 本地开发 HTTP 与 WebSocket 代理验证

变更 `fix-local-dev-proxy`，实现提交 `634b5cb2`。[Issue #432](https://github.com/JayNey/LLM-Algorithm-Harness/issues/432)

## 完整性

- OpenSpec 任务 1/1 完成。增量规格涵盖本地开发服务器和环境配置两个既有要求，严格校验通过。
- 开发模式的 HTTP 和进度 WebSocket 默认使用相对路径。Vite 在回环地址的 3000 端口提供页面，并将两类请求转发至 `127.0.0.1:8000`。前端 README 的启动命令和代理说明与配置一致。

## 正确性

- 修复前，浏览器从 `127.0.0.1:3000` 发起的登录请求直连 `http://localhost:8000/api/v1/auth/login`。新增的 `npm run check:env` 断言在原开发配置下失败，修复后通过。
- 使用锁文件对应的 Vite 8.3.4、Chrome、真实 FastAPI 和独立 SQLite 库验证。分别从 `http://localhost:3000` 与 `http://127.0.0.1:3000` 打开独立浏览器会话。两处都经 Vite 取得真实 API 健康响应、完成页面登录并用 HttpOnly Cookie 请求 `/api/v1/users/me`，HTTP 状态均为 200。
- 两个浏览器会话均从实际开发环境读取进度路径，经应用的 WebSocket 地址解析逻辑连接各自页面主机的 `/api/v1/ws/progress`。FastAPI 接收了两次升级，浏览器收到的 `connected` 帧与 HTTP 用户身份匹配，随后收到 `pong`。
- 直连 API 的跨源预检在修复前后均为 `localhost` 200、`127.0.0.1` 400。相对路径使浏览器请求沿用当前页面来源。

## 一致性与验证命令

- `npm run check:env`、`npm run lint`、`npm run format:check` 与 `npm test` 通过，344 项测试全部通过。
- `npm run build` 和 `vite build --mode test` 通过。Vite 报告现有 CompareCharts 分块超过 500 kB 阈值。
- `git diff --check 398cdda7...HEAD` 和 `comet classic openspec -- validate fix-local-dev-proxy --strict` 通过。
- 实现与精简设计一致，沿用既有 HTTP 客户端、WebSocket URL 解析和会话认证。Tweak 的 `review_mode` 为 `off`，采用上述自动化检查和人工对照。

结论为 PASS。
