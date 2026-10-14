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
- Task 6（接入 run_evaluation_task 替换 mock worker + ORM→domain 转换）: **done**（implementer commit 4bfd795；review-fix R1 commit 7bef2d8；scoped re-review PASS）
  - 风险信号命中：跨模块 + 安全敏感面 + 并发共享状态 + diff>200（399）→ 已派发每任务 reviewer
  - review BASE=4c65318 HEAD=4bfd795，package=.superpowers/sdd/2026-10-13-evaluation-real-executor/review-4c65318..4bfd795.diff
  - **C1 CRITICAL（已修）**：`_to_domain_problem` 逐字传 `source_platform=None`；真实 data/problems.json 12/12 无该键→ORM NULL→domain `source_platform: str=Field("legacy")` 非 Optional→ValidationError→problem_map 恒空→评估全单元 failed（实测 0/12）
    - 修复（commit 7bef2d8）：`DomainProblem(**{k: v for k, v in data.items() if v is not None})` — None 列省略让 domain 默认生效；必需无默认字段缺 None 仍报 field required→并入 missing（失败语义保留）；未改 src/models.py
  - **I1 IMPORTANT（已修）**：集成测试 seed 硬编 `source_platform="leetcode"` 掩盖 C1 → 3 处 seed（orm_row/bad_row/_seed_problem）改为 `source_platform=None` 真实形状，并加断言 `converted.source_platform=="legacy"`/`source_url is None`
  - **scoped re-review PASS（实测）**：真实 data/problems.json 形状端到端转换 12/12 成功；tests/test_celery_tasks.py 22 passed；fix diff 仅 src/tasks/evaluation.py(+11/-1)+tests/test_celery_tasks.py(+9/-3)，无夹带、未改 models.py、无新缺陷
  - B 部分（接线）reviewer 逐项 Spec ✅（session_factory=db.get_bind()、on_unit_finished 计数口径、spent_usd、终态回写、worker 不引用 db、真跑 TaskService 不触网、越界干净）
  - M1 started_at 未写（基线已有、非本次回归，§5.14 只要求 completed_at）；M2 data:dict[str,Any] 放宽；均 deferred
  - fix agent 范围外观察（非阻塞，独立议题）：导入侧对 source_platform 仍落 NULL（若要让 domain 反映真实来源需改导入链路）
  - **tasks.md 2.1/2.2/2.3/3.1 已勾选**（per Preflight checkoff 粒度 Ruling：集成测试全绿后一并勾选，已满足）
- Task 7（resume 去重）: **done**（impl c72741b、review-fix R1 273c180）
  - 前一个 implementer 遭平台配额错误 code 112 中断（已完成测试+人为注入 `if False and ...` 演示 RED）；重派收尾 agent 撤销注入后 GREEN。commit c72741b 仅含 tests (+60 行)，src 无 diff（注入仅为 RED 演示）
  - 风险信号命中 DONE_WITH_CONCERNS → 已派每任务 reviewer：Spec ✅（四项 resume 要求均有断言），无 CRITICAL；**I1 IMPORTANT**：`spent_usd >= first_spent` 在同价 fixture下可被“累加改覆盖”绕过
  - review-fix R1（273c180）：`>=` → `>`（与 reviewer 处方逐字一致，1 文件 +1/-1）；fix agent 提供 mutation-style 证据（注入 spent_usd=cost → 断言 FAIL 于 `0.05 > 0.05`；恢复 → PASS）
  - **Ruling（协调者）**：单字机械断言收紧 + 与 reviewer 处方逐字一致 + fix agent 自带 mutation-style RED/GREEN 证据 + diff 仅 1 行——re-review 唯一信息量（无夹带）已由 `git diff --stat` + 全文 diff 确认；不重派 re-reviewer（走 "Rulings, not stalls"）。如后续任何非机械 fix/多行改动/新增文件，本例外不适用
  - Reviewer 对 concern 3 裁定：「resume 失效→ValueError→failed 路径」已被 Task 6 `test_run_evaluation_task_credential_failure_no_results` 实证覆盖（同一 `except (ValueError, FileNotFoundError)` 分支），可 deferred → verify 阶段观察清单
  - **tasks.md 3.2 已勾选**（见下）
- Task 8（边界测试）: **done**（impl 1132a10；review Spec ✅ PASS，无 CRITICAL/IMPORTANT）
  - 命中 DONE_WITH_CONCERNS → 已派每任务 reviewer（多文件协调 + Alembic schema-adjacent）
  - 覆盖真实缺口：§8 #4 部分题目缺失（集成级）+ #10 聚合口径合并为一条（`test_run_evaluation_task_missing_problem_fails_only_that_unit`）；Ledger Task 1 deferred “既有库迁移不破坏历史行”→ Alembic `upgrade 3a568a0f1b04 → insert model=NULL → upgrade head` 断言行存在 (`test_legacy_evaluation_rows_survive_model_column_migration`)
  - `test_unknown_pricing_does_not_advance_spent` 未重复添加（Task 6 `test_run_evaluation_task_unknown_pricing_honest` 已覆盖同 scenario且断言更强）
  - 验证：`pytest tests/ -k evaluation` 88 passed；`pytest -m "not online"` 1653 passed；`pytest test_celery_tasks.py test_api_database.py` 36 passed；ruff/black/encoding 均绿
  - **Concern 1 语义分歧裁定（协调者+reviewer 一致）**：实跑 `ev.status=="failed"` 为正确终态（TaskService 将任一单元未 completed 的 run 定为 failed），符合 §5.13 「paused/failed 皆可 resume」。若归 completed→resume 不会重跑 failed→与 §5.13 相悖。简报预期 completed 属误读，测试断言按实跑调整保留 failed
  - Reviewer 无 CRITICAL/IMPORTANT，3 MINOR（字面量 total_units=2 不用动态式、raw SQL 硬编列集、父 revision 字面量与迁移链耦合）均 deferred；Task 7 签名 black 一行化合规顺手修复确认
  - Task 2 deferred `model max_length=200` 属源码改动→继续 deferred→verify 阶段或后续统一处理
  - **tasks.md 4.1 已勾选**
- Task 9（CI 门禁）: **done**（impl 4d882d8）
  - 命中 DONE_WITH_CONCERNS（结构性冲突 ruff format ↔ black）→ 派发 reviewer（待派）
  - 修复内容：对 20 个历史 py 文件 ruff format（含本 change 的 `tests/test_api_monitoring.py`）；5 个回退（`src/importers/leetcode.py` + `src/ab_testing.py` 实测拆行使行尾 `# type: ignore` 归属漂移→mypy 错误 1→7；3 个纯风格互斥）。改动 16 files +120/-38，含报告。
  - **Ruling（协调者）**: “CI 等价门禁”的权威定义 = `.github/workflows/ci.yml`（L40-L47 lint job + L74-L75 mypy + L101-L105 radon + L171-L176 pytest）。CI **不** 运行 `ruff format --check`。tasks.md 4.2 初版命令表包含 ruff format --check 属计划侧过度约束。本次已按权威定义重新判定→全绿，并同步修订 tasks.md 4.2 命令表与注释。
  - 实跑协调者直验（全绿）：ruff check ✓ / black --check ✓（286 unchanged）/ find_missing_encoding ✓（0）/ mypy src/ 仅 1 个基线错（api/files/parsing.py:93 SafeLoader，非本 change 文件、base-ref 前已存在）/ test_utf8_io ✓ 18 passed / pytest -m "not online" ✓ **1653 passed, 6 skipped**
  - 残留 ruff format --check 52 个违规（47 md + 5 py）均基线噪音，不属本 change 引入，不在真实 CI gate 范围
  - **tasks.md 4.2 已勾选** + 命令表已按 CI 权威定义重写（删 ruff format --check、补 pytest -m "not online"）

## Verify 阶段集成审查 → verify-fail → 修复闭环（2026-10-14）

整 change 集成审查返回 NOT ready（1 CRITICAL + 5 in-scope IMPORTANT + 1 out-of-scope），执行 `verify-fail`（verify_failures=1）回 build。协调者独立读源码核实 C-1/I-1/I-4/I-6 属实后分 4 批派发修复（TDD）：

- **Fix-A（33eb88b）** C-1 + I-4：`_compute_percentage` helper 分母改 `problem_count × len(strategy_names)` 并 clamp[0,100]，三处调用点（L39/L92/L483）统一；`EvaluationCreateRequest` 加 model_validator 拒重复。协调者独立核实：worker `update_state` 仅写 current/total/message 无 percentage → 实时 async progress 不溢出（Fix-A 顾虑 2 证实不成立）。I-4 返回码 400（项目 errors.py 全局约定）非简报假设 422 → 接受。
- **Fix-B（dbb2562）** I-1 + I-6：`should_pause` 加 `populate_existing()` 跨进程重读 paused；`_EvalContext` 加 `missing_reasons` dict + `_validation_error_summary`，worker 区分「not found」与「invalid/incomplete problem data」（第 5 参默认 None 向后兼容）。28 passed。
- **Fix-C（2d51bc3）** I-3 + I-5：API.md/api-authentication.md 创建/响应示例补 model、改写「worker 返回模拟结果」行为性陈述（保留监控自述句=L441 I-2 out-of-scope）；async-tasks.md 加「真实评估运行前置」节。1662 passed。
- **Fix-A/B/C scoped reviewer（整批 f531ef2..2d51bc3）**：无 Critical；C-1/I-4/I-1/I-6 四项运行时正确性经独立复现（I-1 同构 session 实测 plain→running / populate_existing→paused）判正确、向后兼容、无回归。返回 With fixes，列出文档/spec 验收欠账（Important 1-5）+ 一 Minor（I-4 校验器 details 键退化）。
- **Fix-D（625d479 + 7e09d59）** 收尾 Important：I-4 校验器 model_validator→两 field_validator（details 键定位字段，测试断言收紧为结构化）；422→400 全量订正（文档+注释）；API.md L415 删除「真实评估 worker」对冲项；补 API.md 列表响应示例 + README L559 创建示例 model + README L496 改写；API.md:265 声明进度分母口径；delta spec 追加 2 Requirement（重复拒绝 400 不建记录 / percentage[0,100] 单元分母）5 Scenario + design.md D5 标「已回答」。openspec validate --strict valid。
- **Fix-D scoped re-reviewer（2d51bc3..7e09d59）**：6 项 finding 全 ADDRESSED，无新增 Critical/Important，仅两处 Minor（README:501 段内残留「评估入口仍使用模拟 worker」对冲、spec Requirement total 口径措辞过宽）+ out-of-scope 观察（tasks.md:4 的 422、api-monitoring.md/api-files.md「worker 仍模拟」、API.md 轮询示例 completed==total 在新口径下死循环）。
- **Fix-E（7178395，协调者直改·纯文本无取舍）**：README:501 架构组件项改真实执行；tasks.md:4 422→400；spec.md Requirement 加「进度接口与聚合回退口径」限定 + async_task.progress 例外注（不改代码语义）；API.md 轮询示例退出条件 completed==total → percentage>=100 并加注释。门禁全绿（ruff/black/encoding/openspec valid）。

### Deferred / Follow-up（archive 后另行处理，不阻塞本 change）

- **I-2**（out-of-scope）：monitoring 探针 `evaluation_worker_implementation=mock` 自述（`api/monitoring/probes.py:246`、`task_snapshots.py:106`、`routes/monitoring.py:143`）+ 4 处 monitoring 测试断言 `=="mock"` + 文档 `api-monitoring.md:3`/`api-files.md:116` 同类「worker 仍模拟」陈述 → 独立 capability，需单独 change 更新探针与相关测试与文档。API.md:441 监控自述句本轮刻意未改以与代码现状一致。
- **worker 感知 cancelled 相邻缺口**：`should_pause` 只认 paused，API `cancel_task` 写 cancelled 不被 worker 感知、终态仍会覆盖 → follow-up。
- Minor（非阻塞）：`missing_problems` 只写不读（与 missing_reasons.keys() 等价）字段合并；I-1 新测试 session `try/finally` 收尾；`populate_existing` docstring 前瞻注；`api/models.py` class-based `Config`→`ConfigDict`（Pydantic V3 弃用告警）；幂等键无 DB 级 UNIQUE；`_estimate_cost` 丢定价出处；逐 pid SELECT N 次。
- 已消化：原 M-6（missing_problems 计算未消费）经 I-6 missing_reasons 部分消化，但 missing_problems 字段本身仍只写不读（归入上方 Minor）。

