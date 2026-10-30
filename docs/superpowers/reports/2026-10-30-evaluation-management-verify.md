# evaluation-management 验证报告

## 状态
PASS。3/3 tasks、1/1 requirement、4/4 scenarios 完成；没有未解决的 CRITICAL/IMPORTANT 问题。归档须等待用户最终确认。

## 范围与规格对照
Issue #320；分支 `codex/evaluation-management`；OpenSpec `frontend/app-shell` 增量规格 1 项 requirement、4 个场景，任务 3/3。

- 暂停/恢复：`api/services/evaluation_service.py` 校验当前 AsyncTask 的 ID、所有者、实体与类型，返回 `async_task_id` 和操作能力；`frontend/src/evaluations/client.ts` 调用 `/tasks/{id}/pause|resume`。评估恢复沿用既有 paused 校验及同一任务 ID，不套用其他业务的 stop_confirmed 门槛。
- 预算/删除：服务端投影匹配现有 pending 更新、pending/completed/cancelled 删除规则；客户端 PATCH 只发有限非负预算，DELETE 接受 204；详情页确认删除后返回重新读取的列表。
- 失败/隔离：详情页同步锁和 loading 禁止重复提交；动作通过观察器 runMutation 使先前 HTTP 周期失效，成功/失败均重新 GET；按 route key 重挂载及会话 provider key、AbortController 隔离旧动作。HTTP 认证层继续校验 session marker。
- 多语言/窄屏/键盘：中文与英文文案、关联标签、确认 Modal 支持 Esc 与焦点恢复，320px/1440px 截图及浏览器断言通过。沿用现有 Ant Design 与工作台外观。

## 验证证据
- TDD RED：新增服务端能力回归最初因字段缺失失败；客户端因 async_task_id 未投影失败；页面因无暂停按钮超时。随后实现并转 GREEN。
- `npm test`（frontend）：298/298 通过。
- `npm run build`、`npm run format:check` 通过；`npm run lint` 零错误。
- `python3 -m pytest tests/test_evaluation_workflow_contract.py --no-cov -q`：67/67 通过，包含错误 owner/entity/type 关联与服务端状态矩阵。
- `python3 -m pytest tests/test_evaluation_workflow_contract.py tests/test_task_manager.py tests/test_evaluation_async_flow.py --no-cov -q`：123/123 通过（额外关联参数化后又单独运行上项 67 tests）。
- `python3 -m pytest tests/test_api_evaluations.py tests/test_api_auth.py tests/test_evaluation_service_async.py tests/test_evaluation_async_flow.py tests/test_evaluation_workflow_contract.py --no-cov -q`：187/187 通过；随后按最终状态语义再次执行相关合同测试。
- `python3 -m ruff check` 本次 Python 文件通过；`python3 -m mypy --follow-imports=silent api/services/evaluation_service.py api/schemas.py` 通过。
- `frontend/scripts/verify-evaluation-management.mjs`：15 类断言通过，覆盖最新任务 ID、缺失关联、防双击、超时、400/403/404/409/500 对账、401 登录恢复、删除 204 导航、Esc 取消、路由及登录会话切换；报告 `/tmp/issue320-browser.log`。
- 既有 `verify-evaluations.mjs --scenario detail`：27 项通过；`--scenario progress`：8 项通过；`--scenario create`：39 项通过。证据在 `/tmp/issue320-existing-{detail,progress,create}/`。
- `python3 scripts/verify_evaluation_management.py`：真实 TCP HTTP + 隔离 SQLite/Redis 操作闭环通过，覆盖 Cookie/CSRF、预算、暂停/恢复入队、取消、删除与详情/列表刷新。最终结果 `/var/folders/hd/18z3z0s90l5gl_rqt9qy3szm0000gn/T/issue320-http-a8hwkokx/result.json`。
- `comet classic openspec -- validate evaluation-management --strict` 通过。

## 审查与限制
独立 reviewer 对最终功能 diff 做静态集成审查，未发现可操作的正确性或安全问题；未重复派发最终审查。设计与实现一致，四项 delta 场景均有上述回归覆盖；本流程为 tweak，无独立 Superpowers Design Doc/plan。
真实 HTTP 联调用显式播种的运行中 AsyncTask 验证管理接口，恢复实际发布到隔离 Redis；未触发模型调用，也未验证真实模型执行暂停时的吞吐或费用。
保留已有非阻塞告警：BenchmarkDetailPage 两条 hooks 依赖警告、生产构建已有大 chunk 提示、Pydantic class Config 弃用提示。
最初全量测试在沙箱内遇到 `tests/test_api_cost.py::TestPricing::test_full_model_ids_round_trip_over_http` 等本地 socket fixture 的 PermissionError；已中止并在允许本地监听的环境复跑，无源码修复。

## 全量后端回归
`python3 -m pytest --no-cov -q`：3625 passed、2 failed、11 skipped，日志 `/tmp/issue320-full-pytest-network.log`。

两项失败均在本 change 内完成根因修复：
- `tests/test_api_versioning.py::test_existing_v1_http_contract_is_preserved`：冻结快照未包含新增的五个响应字段。精确更新 EvaluationResponse 的 optional properties（26 行），原有属性、required、路由及认证合同均未变；未放宽合同守卫。
- `tests/test_utf8_io.py::test_repository_has_no_implicit_text_file_or_subprocess_encodings`：新增联调脚本的日志 open 和结果 write_text 缺显式 UTF-8，现已补齐。

最终运行两份测试文件：`python3 -m pytest tests/test_api_versioning.py tests/test_utf8_io.py --no-cov -q`，41/41 通过，包含原来的两项失败及合同破坏拒绝测试。修复只涉及测试快照和联调脚本的编码，不修改业务实现，因此保留其余 3625 项全量通过证据，不重复整套；最终没有未解决的测试失败。最终 HTTP 脚本亦再次通过。

初次沙箱运行中止前的环境错误完整名单（允许本地监听后的全量复跑均通过）：`TestPricing::test_full_model_ids_round_trip_over_http`、`TestPricing::test_full_model_id_auth_and_validation_over_http`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[experiment]`、`test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery[ab]`（均在 tests/test_api_cost.py）。
