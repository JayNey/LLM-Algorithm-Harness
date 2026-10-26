# 真实评估 QA：fixture 与 live 联调

本文把浏览器 fixture 与真实评估联调分开记录。fixture 使用真实 React 页面和路由，但以确定性响应替换业务 API；只有真实账号、API、Redis/Celery、sandbox 和本人 provider key 实际参与的运行才可记作 live。

## 当前预检记录

检查日期：2026-10-26。本次只读检查当前开发机，不读取 `.env` 值、不输出凭证、不连接模型提供方。

| 层级                   | 本次状态                 | 证据与限制                                                                                                   |
| ---------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| 浏览器/UI              | 可由本地 Vite 单独启动   | 这只提供前端页面，不代表 API 可用。                                                                          |
| API                    | 未运行                   | `127.0.0.1:8000` 未监听。                                                                                    |
| PostgreSQL             | 未运行                   | `127.0.0.1:5432` 未监听。                                                                                    |
| Redis                  | 未运行                   | `127.0.0.1:6379` 未监听。                                                                                    |
| Celery worker          | 未运行                   | 未发现 Harness 容器，API/Redis 未运行也无法证明 worker 可用。                                                |
| Docker/sandbox         | 未验证                   | Docker daemon 29.9.2 可访问；没有 Harness worker 容器，因此这不构成 sandbox 预检证据。                       |
| 测试账号与应用 API key | 未提供                   | 当前进程环境未发现 T17 专用测试身份或应用 key 标识；不读取其他用户凭证。                                     |
| 模型提供方与预算       | 未就绪                   | 没有用于此流程的标准 provider key 环境变量或明确的小额调用预算。Codex 主机凭证不作为应用 provider key 使用。 |
| 真实 API/WS/模型结果   | **未进行真实端到端联调** | 没有创建或启动真实评估，也没有真实结果、实时进度或供应商响应证据。                                           |

依赖关系：#232 仍等待 [#231 工程质量与回归](https://github.com/JayNey/LLM-Algorithm-Harness/issues/231) 实际验收和代码合入 main。即使本机有 fixture 通过，也不能替代这项前置或 live 验收。

## Fixture 验证

在 `frontend/` 运行 `node scripts/verify-evaluations.mjs --scenario all` 可检查现有的创建、任务、结果、权限及进度前端路径。使用外部 Playwright 时设置 `PLAYWRIGHT_MODULE`；Vite API base URL 使用项目已有的开发环境配置。

近期外观矩阵另见 [`QA.md` 的 #229 记录](QA.md)。两类浏览器验证都替换了身份和业务 HTTP 响应，不替换真实 API 即不能记录为 live。不要把 fixture 的创建成功、任务状态或截图复制到 live 证据中。

## Live 验收步骤

只有在目标环境真实依赖已准备好后才运行。不要通过 fixture、`route.fulfill`、伪造 WebSocket 或静态结果补齐缺失层级。

1. 等待 #231 验收并合入 main，然后从目标环境确认 API、业务数据库、Redis、Celery worker 和 sandbox 实际可用。仅 health endpoint 通过不足以证明评估链路可用。
2. 使用本人可访问的专用测试账号登录。应用 provider key 通过应用设置配置；密码、API key、cookie、token 和真实 prompt 不写入命令参数、日志、截图、报告或仓库。
3. 确认 provider、模型、额度和单次预算上限。使用一个题目、一个策略和用户明确的小预算；若无额度、权限或预算条件，停止真实请求并记录阻塞原因。
4. 从真实 UI 登录开始创建并启动评估，观察 API 返回的 `evaluation_id`、任务详情、Celery worker 执行、WebSocket/HTTP 进度及结果页。`evaluation_id`、`AsyncTask.id` 与 `run_id` 分别记录，不互相替代。
5. 保存脱敏的 UTC 时间、请求/响应状态码、状态变化、脱敏 ID 和浏览器证据。截图前确认没有用户名、key、cookie、token 或私有题面内容。
6. 若任一依赖未就绪，写明 `未进行真实端到端联调`，列出缺项、受影响的验收层级、负责人可执行的恢复步骤；不声明完成。

## 恢复清单

- 等待 #231 的实现合入 main，并更新到该提交。
- 在用户指定的隔离目标环境启动 API、数据库、Redis、worker、sandbox 和前端；不要将未确认的本地服务视为生产目标。
- 由用户准备专用测试账号、本人有权使用的 provider key 和明确的小额预算；没有这三项时只做依赖检查和 fixture 验收。
- 按上述步骤进行一次 live 运行，补入实际脱敏证据与未覆盖范围，再由维护者决定 #232 的验收状态。

## 本次文档变更检查

- OpenSpec strict validation 通过。
- `prettier --check` 和 `git diff --check` 通过。
- `frontend/npm run build` 通过，只有既有的大 bundle 提示。
- 本 PR 只更新验收文档，没有改运行时代码；未运行真实 API、provider、worker 或 sandbox 调用。
