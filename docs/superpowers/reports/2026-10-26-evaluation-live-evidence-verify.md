# #232 真实联调准备验收

## 范围

本 change 只交付依赖盘点、fixture/live 区分、恢复条件与安全步骤文档。真实端到端联调依赖 #231 和可用的目标环境；本次未启动模型请求，也不把 fixture 结果写成 live 通过。

## 环境盘点

检查日期：2026-10-26。本地 API、PostgreSQL、Redis、Vite 默认端口 8000、5432、6379、3000 均未监听。Docker daemon 可访问（29.9.2），但没有运行中的 Harness 容器。没有可确认用于 T17 的测试账号、应用 API key 或小额预算；未读取 `.env` 内容或任何凭证。API/Celery/sandbox 和 provider 端到端因此未验证。

## 检查结果

- `comet classic openspec -- validate evaluation-live-evidence --strict`：通过；本次 change 仅文档，`.openspec.yaml` 声明 `skip_specs: true`。
- Prettier 与 `git diff --check`：通过。
- `npm run build`：通过，显示既有大 chunk 提示。
- 未运行单元测试或浏览器 fixture：本 change 未改前端实现；现有 fixture 在 [`docs/frontend/EVALUATIONS_QA.md`](../../frontend/EVALUATIONS_QA.md) 单独列出，明确不代表 live。
- 未进行真实登录、API/WS、Redis/Celery、sandbox 或 provider 调用；未生成 live 截图或结果 ID。

## 结论与恢复条件

本地文档验收通过；真实端到端未进行。#231 仍为开放前置项，且本机没有可用 API/数据库/Redis/worker、本人测试身份或预算。待 #231 合入 main，并由用户提供目标环境、专用账号、应用内 provider key 和明确的小额预算后，按 EVALUATIONS_QA.md 的 live 步骤补跑。任何缺项都继续标记为未验证。
