## Context

复用 tests/integration/test_api_workflows.py 的 SQLite、队列 drain 与真实 Celery task.run；复用浏览器 fixture 的 Vite/Chromium、路由、Session Provider、共享 Axios 客户端。任务分支由 Issue 明确授权创建，main 与 origin/main 一致。

## Goals / Non-Goals

覆盖 Issue #230 列出的已有认证和评估契约，保留有效 CSRF 采集及真实中间件。真实 Redis/Celery 网络、供应商与 Docker 沙箱联调属于单独证据层级，本任务的离线通过不代表这些层级已验证。

## Decisions

1. Cookie 测试从真实 register/login 响应和身份 GET 收集 CSRF，不关闭中间件。running 时在模型/沙箱边界观察真实数据库与 HTTP 状态；取消复用队列任务体与现有撤销传输替身。
2. 浏览器通过网络 route 控制 401/403/404 和刷新时序，保留真实认证 store、客户端及路由。用确定性 gate 保持并发与迟到响应可复现。
3. 新增测试先执行；出现失败按 systematic-debugging 调查，再做最小修复。必要时用可恢复的本地 mutation 验证新增安全断言确实能捕获缺失行为，并记录执行证据。
4. JSON 与截图记录替换层级、未知请求、页面异常、命令退出码；shell 仅对仍使用 Mock 的区域断言业务零请求。
5. 实际 RED 暴露旧 identity 响应覆盖新会话（marker、用户名、CSRF）。共享 HTTP 请求记录发出时的 session marker，在接受响应、CSRF 与 401 刷新前检查归属；登录身份回写与失败清理同样检查 marker。回归同时覆盖迟到 200 与 401。

## Risks / Trade-offs

- 浏览器 fixture 不证明后端正确 → 分开运行真实 FastAPI Cookie/CSRF 测试。
- 离线队列不证明 broker/revoke 网络正常 → 明确标记未验证层级。
- 范围扩大 → 超过 tweak 阈值或需要架构协调时交用户决定。
