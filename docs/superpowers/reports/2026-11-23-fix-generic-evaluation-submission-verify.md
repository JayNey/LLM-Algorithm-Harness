# 验证报告：fix-generic-evaluation-submission

日期：2026-11-23。工作区：当前 main，比较基线 `db958ea9eb4ab3889e30668744a8b21d17f158b5` 与本次工作区差异。

## 结论

Issue #512 的通用入口评估提交已复用专用启动规则；发布前任务及 Evaluation.async_task_id 已在独立数据库会话可见。真实 worker 可解析关联，真实 TaskService 编排、结果写入及两层任务状态均完成。实现范围为 3 个生产文件、3 个测试文件，没有数据库结构或其他业务提交机制变更。

| 维度 | 结果 |
| --- | --- |
| 完整性 | 5 项任务已实现并验证；1 个修改需求、9 个场景均有实现及测试依据 |
| 正确性 | 合法草稿返回 201 和关联任务；非法请求不新增任务或发布消息；worker 从 running 到 completed |
| 一致性 | 共用 start_owned_evaluation 和既有 EvaluationService.start_evaluation；符合设计的参数、凭据、额度、事务及响应规则 |

## 检查与证据

1. 修复前运行 `.venv/bin/pytest tests/test_generic_evaluation_submission.py -q --no-cov -k 'owned_draft or missing_or_foreign or repeated_submission'`：6 failed，证明发布时无关联、缺失及他人实体返回 201、重复提交生成第二个任务。日志：`/tmp/issue512-red.log`。
2. 修复后运行 `.venv/bin/pytest tests/test_generic_evaluation_submission.py tests/test_task_submission_authorization.py -q --no-cov`：**38 passed**，含 20 项新测试与 18 项既有白名单/跨用户清理授权回归。日志：`/tmp/issue512-green.log`。
3. `.venv/bin/pytest tests/unit/test_api_endpoints.py tests/test_api_evaluations.py tests/test_evaluation_service_async.py tests/test_async_task_submission.py tests/test_user_evaluation_concurrency.py tests/test_tasks_api.py tests/test_evaluation_async_flow.py tests/test_evaluation_workflow_contract.py -q --no-cov`：**1169 passed**。覆盖真实路由错误映射、专用评估启动、异步发布与并发额度等。日志：`/tmp/issue512-regression.log`。
4. 对全部 6 个交付 Python 文件运行 `.venv/bin/black --check`、`.venv/bin/ruff check`：通过。`git diff --check`：通过。
5. `comet classic openspec -- validate fix-generic-evaluation-submission --strict`：通过。
6. 额外 `.venv/bin/mypy api/routes/tasks.py api/routes/evaluations.py` 返回 1，报告 8 个错误。用 `--shadow-file` 加载 HEAD 中的原文件重跑同一检查，仍为同样 8 个错误；忽略行号后逐项计数比对完全一致。问题为 Celery/SciPy 缺少类型声明、既有 evaluation_results 参数类型，以及两个路由原有的 Any/缺少注解/时间字段类型。**没有新增类型诊断，但不能宣称 mypy 全绿**。日志：`/tmp/issue512-mypy.log`、`/tmp/issue512-mypy-baseline.log`。

## 需求场景对应

| Delta 场景 | 实现和测试 |
| --- | --- |
| 通用任务创建先落库 | 原 enqueue_task 及复用的 start_evaluation；test_owned_draft_has_committed_link_before_publication、test_generic_create_route_commits_before_publish |
| 通用任务发布失败 | enqueue_task 原有失败状态；test_broker_failure_is_recorded_and_draft_can_retry、test_generic_create_route_marks_failed_when_publish_raises |
| 拒绝公开提交内部清理任务 | 原白名单在分支前校验；test_public_submission_cannot_delete_cross_user_tasks |
| 拒绝未知任务或类型名称不匹配 | 原白名单保持；test_public_submission_rejects_unknown_or_mismatched_tasks |
| 通用入口提交自有评估草稿 | start_owned_evaluation 与原子提交服务；发布前独立会话断言及 test_submitted_task_runs_real_worker_to_completion |
| 拒绝缺失或他人的评估 | 共用 credential_id 的所有者查询；test_missing_or_foreign_evaluation_is_rejected |
| 拒绝重复或非法状态 | 既有 start_evaluation 状态/重复检查和条件更新；test_non_pending_evaluation_is_rejected、test_repeated_submission_preserves_original_task |
| 规范化并拒绝不一致参数 | tasks.create_task 中参数校验；合法位置参数的 3 个变体与 test_untrusted_execution_parameters_are_rejected |
| 凭据与额度检查 | 共用 auth.owned_key、既有容量检查及 429 映射；test_unavailable_credential_is_rejected、test_capacity_rejection_preserves_draft |

## 范围、审查与限制

- 当前配置为 tweak/direct/direct/off；按已确认配置未派发独立审查。本会话已核对最终生产差异、测试、需求场景及设计一致性，没有发现新增 CRITICAL/IMPORTANT 问题。
- 测试使用真实 HTTP 路由、SQLite、认证凭据存储、评估服务、worker 函数、TaskManager、TaskService 和结果持久化。替换 broker 发布/状态/进度传输及模型和沙箱执行边界，不依赖真实 Redis、Docker 或付费模型。
- 验证覆盖受影响的验收范围，未运行仓库全量测试；未进行生产部署或真实网络模型调用。
- 测试中的已有 Pydantic/pytest-asyncio/datetime 弃用警告保留；额外 mypy 的 8 条基线错误未在本次范围中修复。
- 验证过程中修正了两个测试夹具问题：白名单测试改由迁移初始化数据库，worker 示例题目使用满足既有长度约束的描述。之后相关测试全部通过。
