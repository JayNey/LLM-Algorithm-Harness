# Verify Report — evaluation-real-executor

Date: 2026-10-14
Phase: verify
Base ref: b76aabb
Head: 7178395 (branch comet/evaluation-real-executor)
Scale: full (9 tasks / 63+ files)
Verify result: **PASS**（经 1 轮 verify-fail→build 修复闭环）

## Build Phase Recap

- All 9 tasks.md items checked off (1.1/1.2/2.1/2.2/2.3/3.1/3.2/4.1/4.2).
- All 45 plan step checkboxes checked.
- Task-level reviews all PASS after review-fix rounds for Task 6 (C1+I1) and Task 7 (I1).
- CI-equivalent gates verified against `.github/workflows/ci.yml`: ruff check ✓, black --check ✓ (286 unchanged), find_missing_encoding ✓ (0), mypy src/ — 1 pre-existing baseline error (`api/files/parsing.py:93` SafeLoader), test_utf8_io ✓ (18 passed), pytest -m "not online" ✓ **1653 passed / 6 skipped**.
- Build guard: 13/13 PASS.

## Whole-Branch Integration Code Review Findings

Reviewer verdict: **Ready to archive? No (C-1 处置后为 With fixes)**.

### CRITICAL (Must Fix)

- **C-1 Multi-strategy progress percentage overflow** — `api/services/evaluation_service.py:39`/`:93`/`:483-491` computes `percentage = completed_count / problem_count * 100`. Post-Task 8 §5.11 语义 `completed_count` = 单元数（策略×题目），`problem_count` 仍是题目数 → 2 策略 × 2 题目 → percentage=200.0 → `api/schemas.py:59-61` `Field(le=100)` 抛 `ValidationError` → `GET /evaluations` 列表端点无 `call()` 包裹 → **HTTP 500**；`GET /evaluations/{id}` / `/progress` → HTTP 400. 旗舰场景（spec §8 #1 2×2）实测触发。
  - 修法：分母改为 `problem_count * len(strategy_names)`；补 API 级回归测试（真实 2×2 完成评估 → GET /evaluations 200）。
  - 归属：base b76aabb 数学已存在（旧 mock 也让 `completed_count = record.completed_units`），但本 change §5.11 重新定义口径后未同步下游消费。Reviewer 与协调者均认定属"计划侧欠账"。

### IMPORTANT (Should Fix)

- **I-1 `should_pause` 用户暂停分支跨进程永不生效** — `src/tasks/evaluation.py:184-186` 用 `db.query(AsyncTask).filter(...).first()`，但 `expire_on_commit=False` + identity map 命中已加载实例 → API 进程 `pause_task()` 写 `"paused"` 对本 worker 不可见。§5.10 声称复用既有 should_pause，spec 「被预算**或用户**暂停」的"用户"分支不成立。修：`db.refresh(current_async_task)` 或 `populate_existing()`；补一条用第二 session 写 paused 的集成测试。
- **I-2 监控自申报 `evaluation_worker_implementation="mock"`** — `api/monitoring/probes.py:246`、`task_snapshots.py:106`、`routes/monitoring.py:143` 三处硬编码 "mock"/`real_evaluation_available=False`，4 处 monitoring 测试断言 `== "mock"`。**Scope 分析**：本 change tasks.md 4.1 明确"补齐受影响测试"清单包括 `tests/test_evaluation*`、`test_api_database.py`、`test_api_auth.py` 等；monitoring 是**独立 capability**、不在本次 change 声明范围。**协调者裁定：deferred → 建立 follow-up issue**（archive 前需在 ledger 显式记账）。
- **I-3 API 文档未跟 BREAKING `model`** — `API.md:91-99`/`API.md:358-364`/`API.md:390-396`/`docs/api-authentication.md:55-61` 创建示例缺 `model`（422）；`API.md:100-120` 响应示例缺 model 字段；`API.md:409`/`:437`/`docs/api-authentication.md:67` 仍写「异步评估 worker 返回模拟结果」。修：更新示例、删除「worker 仍是模拟」的失真陈述。
- **I-4 重复 `strategy_names` / `problem_ids` 语义未定** — open design D5 (design.md:59) 明确要求 Design Doc §5.12 定义口径但 §5.12 未回答。当前 `["vanilla","vanilla"]` → 2 单元、1 行 EvaluationResult、`completed_count=2`、`spent_usd` 累加两次。修首选：`EvaluationCreateRequest` 加 validator 拒绝重复列表。
- **I-5 Docker/CWD 硬前置未进部署文档** — `SandboxConfig()` 默认 backend="docker"、`_prepare_strategy_runtime.health_check()` 失败抛 RuntimeError；`TaskService(root=f"data/tasks/{id}")` 相对 CWD。`docs/deployment/async-tasks.md` 无相应段落。§7 preflight fail-fast 是对的，但部署文档必须写成前置条件。修：追加"真实评估运行前置"章节（Docker 守护 + 镜像预拉 + worker CWD 约定）。
- **I-6 ORM 行非法时的失败原因被伪装成「题库查不到」** — `_resolve_execution_context:392-396` ValidationError → 并入 missing，worker 抛「Problem ... not found」。用户看到「not found」会去重复导入数据集而不是修那行脏数据。修：`_EvalContext.missing_reasons: dict[str, str]` 携带 ValidationError 摘要；worker 抛出记录文本（顺带消化 M-6 死状态）。

### MINOR（不阻断放行）

- M-1..M-11（详见 reviewer 输出）：resume 测试弱断言、worker 不引用 db 无守卫、§8 #9 只覆盖 ValueError 分支、started_at 未写、Task 2 model max_length、missing_problems 计算未消费（与 I-6 同修）、幂等键无 DB 级 UNIQUE、终态映射无兜底、`_estimate_cost` 丢定价出处、逐 pid SELECT N 次、任务 9 ruff/black 结构性互斥应工具链层裁定。

## Coordinator Rulings on Scope

| Finding | Ruling | Reasoning |
|---|---|---|
| C-1 | In scope → must fix | §5.11 语义变更由本 change 引入，下游 consumer 同步是本 change 责任 |
| I-1 | In scope → must fix | §5.10 spec「被预算或用户暂停」明示用户暂停 |
| I-2 | **Out of scope → follow-up issue** | monitoring 是独立 capability，tasks.md 4.1 未列 monitoring 面 |
| I-3 | In scope → must fix | BREAKING 变更声明由本 change 引入，用户可见文档必须同步 |
| I-4 | In scope → must fix | open design D5 已提出，本 change Design 未回答 |
| I-5 | In scope → must fix | 本 change 首次让 Docker 成为评估运行时硬前置 |
| I-6 | In scope → must fix | spec 「写明缺失原因」由本 change 引入 |

## Decision (2026-10-14)

用户选择「继续修复闭环」。按 comet-verify Step 1b（`verify_failures=0`，未达 3 次上限），C-1 + I-1/3/4/5/6 属范围内必须修复项，自动执行 `verify-fail` 回 build 修复，不构成"是否修复"伪决策。

协调者已独立核实（读取源码，非仅凭 reviewer 报告）：
- C-1 属实：`evaluation_service.py:39`/`:92-96` 用 `completed_count/problem_count*100`；`evaluation.py:167` 的 `completed_count` 现为单元数（策略×题目），`problem_count` 仍为题目数 → 2×2 时 percentage=200 → `schemas.py:59-61` `le=100` 抛 ValidationError。
- I-1 属实：`evaluation.py:184` `db.query(AsyncTask).filter(...).first()` 在 `expire_on_commit=False` 下命中 identity map，跨进程 `paused` 不可见。

### Fix 批次（回 build 派发）

- Fix-1：C-1 进度分母改 `problem_count * len(strategy_names)` + API 级 2×2 回归测试（`GET /evaluations` 200）。
- Fix-2：I-1 `should_pause` 用 `db.refresh`/`populate_existing` 重读 + 第二 session 写 paused 的集成测试；同文件顺带 I-6 `missing_reasons` 携带真实失败原因。
- Fix-3：I-4 `EvaluationCreateRequest` validator 拒绝重复 `strategy_names`/`problem_ids` + 测试。
- Fix-4：I-3 文档（API.md + docs/api-authentication.md 创建示例补 model、删「worker 模拟」陈述）；I-5 部署文档追加「真实评估运行前置」章节（Docker 守护 + 镜像预拉 + worker CWD 约定）。

### Follow-up（out-of-scope，本次不修）

- **I-2** monitoring 自申报 `evaluation_worker_implementation="mock"`（`api/monitoring/probes.py:246`、`task_snapshots.py:106`、`routes/monitoring.py:143`）：monitoring 是独立 capability，不在本 change tasks.md 4.1 声明范围。建立 follow-up：归档后单独 change 更新 monitoring 探针与相关测试。

## 修复闭环结果（Fix-A..E）

| 批次 | commit | 覆盖 finding | 验收 |
|---|---|---|---|
| Fix-A | 33eb88b | C-1 + I-4 | `_compute_percentage` 三处统一 + clamp；重复拒绝 validator；RED→GREEN |
| Fix-B | dbb2562 | I-1 + I-6 | `populate_existing` 跨进程重读；`missing_reasons` 真实原因；28 passed |
| Fix-C | 2d51bc3 | I-3 + I-5 | 示例补 model + 删失真陈述 + 运行前置节；1662 passed |
| Fix-D | 625d479 + 7e09d59 | reviewer Important 1-5 + Minor | field_validator、​422→400、L415 矛盾、README/列表 model、进度口径声明、delta spec 新契约、design D5 已回答；openspec validate --strict valid |
| Fix-E | 7178395 | re-review 残留 Minor | README:501 模拟 worker 残留、tasks.md:4 422→400、spec total 口径限定、API.md 轮询示例退出条件 |

审查链：Fix-A/B/C 整批 scoped reviewer（无 Critical，4 项运行时正确性经独立复现）→ Fix-D scoped re-reviewer（6 finding 全 ADDRESSED，无新增 Critical/Important）。

## Spec 漂移处理

verify 检查项 6 发现 delta spec 新增两条契约（I-4 重复拒绝、C-1 percentage 单元分母）而 Design Doc 未体现（重复输入正是 open D5 遗留）。用户选择**方案 A**：在 Design Doc 新增 §5.15 Implementation Divergence 补记两项设计决策（本阶段允许产物，零代码风险）。

## 最终验证结果（PASS）

- tasks.md 9 项 + plan 45 step 全 `[x]`（build guard 13/13 PASS）。
- 实现符合 OpenSpec design.md 高层决策与 Design Doc（Option A 复用 harness 内部方法、TaskService 逐单元编排、线程边界、幂等 upsert、聚合口径、预算/用户暂停、resume 去重）；scoped reviewer 独立复现 I-1 跨进程根因与修法、穷尽 C-1 溢出计算面。
- 能力规格场景：delta spec 各 Scenario（含新增 I-4/C-1 契约）均有覆盖测试。
- proposal 目标（mock worker → 真实 AlgorithmHarness）已满足。
- delta spec ↔ Design Doc 无矛盾（§5.15 已补记）。
- CI 等价门禁全绿：ruff check / black --check（275 files unchanged）/ find_missing_encoding（0）/ mypy src/（仅 1 基线错误 `api/files/parsing.py:93` SafeLoader，非本 change 文件）/ pytest test_utf8_io / **pytest -m "not online"：1662 passed, 6 skipped**。
- 结论：**Ready to archive**（待用户确认归档）。follow-up：I-2 monitoring 探针、worker 感知 cancelled、若干 Minor（见 ledger）。
