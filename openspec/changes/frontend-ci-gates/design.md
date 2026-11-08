## Context

现有生产镜像以 Node 24 构建 SPA。直达路由脚本可自行启动 Vite preview，实验创建脚本可通过环境变量指向预览服务。

## Decisions

- 在现有 CI 的 PR 触发器下配置独立的前端检查和浏览器 smoke。使用 Node 24，按前端 lockfile 执行 `npm ci`。
- 通过 `npm run lint`、`npm test` 和 `npm run build` 检查前端。构建脚本先运行 `tsc -b`。
- 为 smoke 安装锁定版本的 Playwright Chromium，用生产构建运行直达路由和实验创建场景。复用 #400 的身份、通知和实验 API fixture。
- 将 smoke 报告写入运行器临时目录，验证命令的退出码能传播至各自的 CI 检查。
