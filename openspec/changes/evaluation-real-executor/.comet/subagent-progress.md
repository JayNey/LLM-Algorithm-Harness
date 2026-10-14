# Subagent Progress — evaluation-real-executor

- Plan: docs/superpowers/plans/2026-10-13-evaluation-real-executor.md
- review_mode: standard（仅风险任务派发每任务 reviewer，最多 1 轮 review-fix）
- tdd_mode: tdd（每个 implementer 先加载 test-driven-development，提供 RED/GREEN 证据）
- isolation: branch → comet/evaluation-real-executor
- base-ref（plan）: b76aabbddf104e526b3ac59433c34dcf90f71f07
- design-artifacts baseline commit: e9eb05c7d5235762abae6b1dcef0155bc4563ccd

## Preflight 裁决

- Ruling: `_record_unit_result` 只做 EvaluationResult 幂等 upsert + 返回 cost，不设置 completed_count/failed_count；计数聚合统一在 Task 6 的 on_unit_finished 按 record.units 全量重算（幂等、resume 无漂移，符合 Design Doc §5.11）。原 Task 4 计数断言移除，由 Task 6/Task 8 覆盖。
- Ruling（tasks.md 勾选粒度）: plan 把 OpenSpec tasks.md 2.1/2.2/2.3 拆成单元级 helper（plan Task 3=_resolve_execution_context、Task 4=_record_unit_result、Task 5=_build_harness+worker+成本+预算），但 tasks.md 2.1/2.2/2.3 的「验证」是集成级（凭证失败→评估 failed 且无 EvaluationResult 行 / 每单元一行结果 / 预算触顶→paused），这些只有在 plan Task 6 接线 run_evaluation_task + 集成测试后才为真。故 Task 3/4/5 完成时**不勾选** tasks.md 2.1/2.2/2.3（避免断言未运行的验证）；这三项连同 3.1 在 plan Task 6 集成测试全绿后一并勾选。Task 3/4/5 的完成以本 ledger + plan 记录为准。
- Ruling（测试文件位置）: 新建 eval-task 测试统一加入现有 `tests/test_celery_tasks.py`（已有 db_session/evaluation_setup fixture 且已 import run_evaluation_task），不新建 plan 里提到的 tests/test_evaluation_task.py；Task 4-8 沿用此约定。
- Ruling（Task 5 预算暂停测试提前依赖）: plan Task 5 Step 1 的 `test_budget_pause_stops_scheduling` 需要完整 run_evaluation_task 接线（on_unit_finished 累计 spent_usd + should_pause + task_service.run），而这些都是 Task 6 的产物；Task 5 只产 `_build_harness` + `worker`，无法独立跑预算暂停。且 Task 6 plan Step 1 已含 `test_run_evaluation_task_budget_pause`（断言 paused + completed_count<4）覆盖同一行为。故裁定：Task 5 **跳过** `test_budget_pause_stops_scheduling`（重复/提前），只实现 `test_worker_returns_real_result_with_cost` + `test_worker_missing_problem_raises` + `_build_harness` 单测；预算暂停集成验证归 Task 6。
- Ruling（worker 可测接缝）: Task 5 把 worker 实现为模块级工厂 `_make_worker(harness, strategy_configs, runtimes, problem_map) -> Callable[[TaskUnit], ExecutionResult]`（返回闭包），以便独立测试且 Task 6 可在 run_evaluation_task 内调用；worker 闭包**绝不引用 db**（executor 线程安全）。

## Task 状态

- Task 1（Evaluation.model 列 + 迁移）: **done**（commit 6859275，review clean；Spec ✅）
  - deferred minor: 非空库迁移不破坏历史行无测试 → Ruling: 挂到 Task 8 补（已写入 plan Task 8 Step 1）
  - deferred minor: 迁移 docstring 空行 nit（不影响门禁）
  - 给 Task 2 的提醒：EvaluationResponse 需同步加 model 字段才能断言持久化；字段名 `model` 不触发 Pydantic protected_namespaces 警告
- Task 2（EvaluationCreateRequest.model 必填 + 持久化）: **done**（commit 091c4f0；review Spec ✅，无 CRITICAL/IMPORTANT）
  - 风险信号命中公共 API 契约变更 → 已派发每任务 reviewer，结论 clean
  - Ruling: reviewer MINOR（请求 model 缺 max_length=200，与 DB 列 String(200) 及邻字段 api_key_id 约定不一致）——不构成 spec 缺口（spec 仅要求 min_length=1），且主会话禁改源码，本轮不触发 review-fix；deferred，如需可在 Task 8/后续统一补
  - 给 Task 3 的接口：Evaluation.model 已可空持久化；创建路径经 EvaluationCreateRequest.model 必填注入
- Task 3（_resolve_execution_context fail-fast）: **done**（commit 9b2fe7d；review Spec ✅，无 CRITICAL/IMPORTANT）
  - 风险信号命中安全敏感面（凭证/Fernet 解密路径）→ 已派发每任务 reviewer，结论 clean
  - 顾虑1（api_key_id 额外守卫）裁定：reviewer 接受为合理等价强化（语义等价、门禁驱动、未越界、有独立 RED）
  - deferred MINOR→Task5/6 交接备注：① AuthService(AuthSettings()) 构造在 try 外，接线时确认配置类异常归入不可重试的 ValueError 分支；② 接线时传入与 evaluation 同一 business engine 的 session_factory
  - **tasks.md 2.1 未勾选**（见 Preflight 勾选粒度 Ruling，集成验证随 Task 6）
- Task 4（_record_unit_result upsert）: **done**（commit bdecbd5；review Spec ✅，无 CRITICAL/IMPORTANT）
  - 风险信号自报跨模块协调（轻度）→ 已派发每任务 reviewer，结论 clean；幂等有硬证据（count()==1）、不写计数/不 commit 裁定经核验为真
  - deferred MINOR：① 测试名 test_record_completed_unit_upserts_and_counts 含 "counts" 但不断言计数（命名误导，cosmetic）
  - → Task 5/6 交接备注：② 确认 ExecutionResult.status 枚举全集 ≤16 字符（budget_exhausted 恰 16）；③ 幂等仅靠应用层 query-first，无复合 UNIQUE 约束，max_workers=1 单线程下无并发重复风险（如未来并发需补 DB 级唯一约束）
  - **tasks.md 2.2 未勾选**（集成验证随 Task 6）
- Task 5（_build_harness + 真实 worker + 成本 + 预算暂停）: **done**（commit 45d3229；review Spec ✅，无 CRITICAL/IMPORTANT）
  - 风险信号命中（跨模块/并发共享状态/diff>200=228）→ 已派发每任务 reviewer，结论 clean；worker 闭包经字节码验证不引用 db
  - **Task 6 硬前置（顾虑#2，reviewer 已裁定属 Task 6）**：`_EvalContext.problem_map` 装 ORM `api.db.models.Problem`，而 `_execute_problem` 需 domain `src.models.Problem`；接线前必须补 ORM→domain 转换
    - 协调者已查实：ORM Problem 列与 dataset 字段 1:1（problem_id/title/description/difficulty/tags/constraints/test_cases/source_platform/source_url）；domain Problem 有 `migrate_legacy_test_cases`(mode=before) validator 接受 `test_cases` 键→归为 public_test_cases（hidden 为空，migration_status=legacy_test_cases_as_public）。转换=`Problem(**row_dict)`（或 ProblemLoader().load_from_dict），字段均为 eagerly-loaded 列，安全
    - 数据限制：DB 导入题目只有 public 测试（无 hidden），真实执行按 public 评测——诚实的数据层限制，非代码 bug
  - MINOR→Task6 必补：集成测试覆盖 `cost_unknown=True`（无定价→cost 0.0不伪造）诚实口径分支
  - MINOR：未知策略在 worker 报 KeyError（非 ValueError）；_build_harness 阶段已 fail-fast，正常路径不触
  - **tasks.md 2.3 未勾选**（集成验证随 Task 6）
- Task 6（接入 run_evaluation_task 替换 mock worker + ORM→domain 转换）: implementing
- Task 7（resume 去重）: pending
- Task 8（边界测试）: pending
- Task 9（CI 门禁）: pending
