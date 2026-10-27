# Issue #230 归档后交付草稿

PR 标题：`test: cover evaluation workflow auth and integration`

PR base：`main`。分支：`codex/issue-230-evaluation-auth-integration`。归档前草稿状态：尚未推送或创建 PR。用户已于 2026-10-27 明确选择 C：确认归档、立即推送并创建 PR，同时更新 Issue #230 验收结果。

## PR 正文

评估离线验收此前缺少真实 Cookie/CSRF 生命周期和共享认证客户端的浏览器安全回归。本 PR 复用现有 SQLite、队列 drain 与真实 worker 任务体，覆盖 create/start/running/results、排队和运行中取消、403、跨用户404、CSRF 与 refresh/revocation；同时修复旧 `/users/me` 的迟到200/401可覆盖或清除新会话的问题，并校正 shell 对仍 Mock 区域的请求边界。

Refs #230。基线 `f507b568caf21abd7e325a88a7851afce5a37a03`，包含前置 #229 / PR #282；复用 main 中已有 #216–#229 的公开接口与实现。

验证（退出码均为0）：

- 聚焦 HTTP：199 passed。
- 前端单元测试：257 passed；类型检查、生产构建、ESLint、格式检查、Python wheel 构建通过。
- 浏览器 all：149项主流程断言，appearance子进程216项断言；security独立8项，shell51项。未知 API 与未处理页面异常均为空。
- 独立只读集成审查：无 CRITICAL / IMPORTANT；迟到identity的实际 RED 及CSRF断言敏感性RED、检查JSON和截图随PR保存。

验收报告与完整命令：[`docs/superpowers/reports/2026-10-27-evaluation-auth-integration-verify.md`](docs/superpowers/reports/2026-10-27-evaluation-auth-integration-verify.md)。证据位于 `docs/superpowers/reports/assets/issue230/`。

验证层级：离线HTTP保留真实FastAPI认证/CSRF中间件、SQLite与worker任务体，仅替换模型、沙箱和队列/Redis传输；浏览器HTTP和WebSocket响应由fixture拦截，保留真实React、路由、共享Axios与会话存储。未验证真实browser↔FastAPI Cookie/CORS/Set-Cookie竞态、Redis/Celery网络、供应商、Docker沙箱、真实上游WebSocket、Safari/Firefox及真机；不以fixture通过代表这些层级联调完成。整体质量/真实联调/交付汇总仍由#231/#232/#233跟踪。

已知既有提示：Pydantic弃用警告、BenchmarkDetailPage的2个hook dependency warnings、Vite大chunk提示；本次修改文件定向lint无warning。

## Issue 验收更新

实际创建 PR 后，将以下占位符替换为可访问的 PR 和报告链接，并更新 Issue #230。

Issue #230 的离线实现与验收已完成，关联 PR：PR_URL_PLACEHOLDER（base: main，基线 f507b568，含前置 #229 / PR #282）。

- [x] Cookie create→start→running→results、排队/运行中取消；evaluation/task/run/checkpoint标识分离。
- [x] 并发401共享一次刷新；失败清除会话并保留回跳URL；403不清会话；两用户404；缺失/错误/合法CSRF；旧identity迟到200/401不改新会话。
- [x] 实际迟到identity RED→修复→GREEN，CSRF断言敏感性RED→正常进程GREEN；未关闭中间件。
- [x] HTTP199、前端单元257、browser all149+appearance216、security8、shell51；均退出0，无未知API或未处理页面异常。
- [x] 独立只读代码审查无CRITICAL/IMPORTANT；报告、JSON、截图与命令退出码随PR提交。

证据：REPORT_URL_PLACEHOLDER。

分层限制：HTTP为真实FastAPI/SQLite/worker任务体的离线测试，替换模型、沙箱及Celery/Redis传输；browser为拦截HTTP/WS的fixture。真实browser↔FastAPI Cookie/CORS/Set-Cookie竞态、Redis/Celery网络、供应商与Docker沙箱未验证，真实联调与总体验收继续由#231/#232/#233跟踪。此处保留issue开启，合并与最终关闭按项目验收执行。
