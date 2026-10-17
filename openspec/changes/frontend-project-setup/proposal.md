## Why

仓库目前只有后端 API 与 CLI，没有可运行的 Web 前端。Issue #160 要求先把 `frontend/` 的工程骨架、构建配置和基础路由立起来，后续页面才能在同一套工具链上开发。

## What Changes

- 在 `frontend/` 用 Vite + React 18 + TypeScript 初始化应用，并按约定建立目录骨架。
- 配置开发服务器（端口 3000、热重载、`/api` 代理到本机后端）、路径别名和生产构建。
- 配置 ESLint、Prettier、EditorConfig，以及只覆盖前端暂存文件的 husky + lint-staged。
- 采用 Tailwind CSS，包含响应式断点和 class 策略的深色模式。
- 提供开发/生产环境变量：API Base URL、WebSocket URL、应用名和功能开关。
- 安装路由、状态、HTTP、WebSocket、UI、图表、表格、编辑器、日期和表单依赖；页面仅保留可导航的占位路由，不实现业务界面。
- 忽略 `frontend/node_modules`，避免依赖进入版本库。

## Capabilities

### New Capabilities

- `frontend/app-shell`: 前端工程可安装、可开发、可构建，并能通过环境变量与基础路由连上现有后端。

### Modified Capabilities

## Impact

- 新增 `frontend/` 工程及根目录 `.gitignore` 中的 Node 依赖忽略规则。
- 开发时代理指向现有 `http://localhost:8000` 的 `/api`（含 `/api/v1`）；WebSocket 地址对齐现有 `/api/v1/ws/progress`。
- 不修改后端 API、数据库或既有 CLI/报告 spec。
- 新增 npm 依赖；Git 钩子只检查 `frontend/` 下暂存的前端文件。
