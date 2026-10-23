## Context

详情路由与 EvaluationClient 已存在；创建协调器在 201 后自动启动，详情挂载不得重复启动。

## Goals / Non-Goals

完成 #224 手动 GET 刷新和动作；观察控制器由 #225 负责，本轮不轮询。

## Decisions

- useEvaluation 按 owner/client/evaluationId 隔离 GET，清理 AbortController 并拒绝迟到结果；刷新失败保留同一任务的快照但禁用旧操作能力，403/404 隐藏数据。
- 在现有创建协调器中增加独立的详情 action 状态并共用操作锁，不改写创建 phase、ID 和草稿。详情启动/取消先 GET 核对相应能力；页面生命周期 AbortSignal 使离页或切换 ID 的预检失效，在 POST 前再次检查。创建未知不阻止操作已核对的既有 ID。详情动作最终重新 GET，始终展示服务端事实，不在本地写 running/cancelled。
- 回执错误仅在 ID 匹配时展示；动作期间锁住启动和取消，创建自动启动结束后刷新。保持既有 Frontier 外壳、风格、主题与导航。

## Risks / Trade-offs

- 取消可能输给完成 → 无论动作是否成功都刷新，展示错误与最终快照。
- GET 失败可能保留旧信息 → 明示失败，禁用动作直到成功刷新。
- fixture 仅证明浏览器与客户端行为 → 报告分层记录，真实 Redis/Celery、供应商和沙箱未验证。
