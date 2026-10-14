---
comet_change: evaluation-real-executor
role: technical-design
canonical_spec: openspec
---

# 真实评估执行体 — 技术设计（Design Doc）

> 本文是对 open 阶段 `openspec/changes/evaluation-real-executor/design.md`（高层框架 D1–D7）的**实现层深化**，不替代 proposal/spec。canonical 需求以 OpenSpec delta spec 为准：
> - `specs/api/evaluation-execution/spec.md`（新能力）
> - `specs/api/database-schema/spec.md`（`evaluations` 新增 `model` 列）

## 1. 意图与背景

`src/tasks/evaluation.py` 的 `run_evaluation_task` 已具备完整的 DB 中心逐单元编排（TaskService、resume、`pause_when`、`on_unit_finished`、终态映射），唯一缺口是 [worker()](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py#L160-L168) 返回 `{"mock": True}` 的占位实现。本设计把 worker 真实化：每个 (策略 × 题目) 单元经 `AlgorithmHarness` 的执行内核真实调用 LLM + 沙箱，产出真实度量落 `EvaluationResult`，累计真实花费到 `Evaluation.spent_usd`，并复用既有暂停/恢复语义。闭合 issue #149 拆分出的 ① 项。

## 2. 目标 / 非目标 / 反目标

**目标**
- worker 真实执行，产出真实度量，杜绝任何 `mock` 成功结果。
- 逐单元 upsert `EvaluationResult`，聚合 `completed_count`/`failed_count`/`spent_usd`。
- 复用 `AlgorithmHarness` 的执行、成本估算与失败分类，保证与 CLI/experiment 口径一致。
- 复用 `TaskService` 的预算暂停与 resume 去重。

**非目标**
- 不实现 #154 预算管理 API、#155 结果查询/分析 API（仅落库，不新增读取端点）。
- 不改动 #149/#181/#182 已定稿的入队时序、状态机与 `start/pause/resume/cancel` 生命周期。
- 本次不持久化、不接入 `timeout_seconds` / `max_concurrency`（用户已确认，见 §6）。
- 测试不发起任何在线 LLM/沙箱调用。

**反目标（即使技术可行也不做）**
- 不为了并发吞吐牺牲预算严格暂停：`max_workers` 必须保持 1（见 §6）。
- 不在成本无定价时伪造 USD 数值（继承 issue #15 的诚实口径）。

## 3. 约束

- `auth.llm_config(key_id, user_id, model)` **必须传 model**（[service.py:235](file:///Users/charlesleclerc/LLM-Algorithm-Harness/api/auth/service.py#L235)）；stored key 无默认 model → `Evaluation` 必须有 `model` 列。
- `HarnessConfig` 必填 `llm_config` + `dataset_path`（[models.py:764](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/models.py#L764)），但 `AlgorithmHarness.__init__` 不校验 `dataset_path` 存在性、不加载数据集；只要不调用 `_load_problems()`/`run()`，`dataset_path` 可传占位常量。
- `TaskService._serialize_result` 接受 `BaseModel`（[task_service.py:498](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py#L498)），worker 可直接返回 `ExecutionResult`。
- `TaskService.run` 预算严格暂停要求 `max_workers=1`（[task_service.py:343-345](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py#L343-L345)）。
- `on_unit_finished(record, unit)` 在 `run` 调用线程执行；worker 在 `ThreadPoolExecutor` 线程执行 → **worker 不得触碰 `db` session**（线程边界，见 §5.7）。
- Alembic 迁移链 head = `3a568a0f1b04`（`0001 → 0002 → 3a568a0f1b04`），新迁移 `down_revision="3a568a0f1b04"`；迁移由 `api/db/migrate.py:run_migrations` 在启动时执行，无需 alembic.ini。

## 4. 架构总览与数据流（Option A：复用 harness 内部方法）

```
run_evaluation_task(evaluation_id)
  ├─ 加载 Evaluation + AsyncTask（既有）
  ├─ 验证 strategy_names / problem_ids 非空（既有）
  ├─ [新] 验证 evaluation.model 非空 ── 缺失 → ValueError → failed，无单元结果
  ├─ [新] auth = AuthService(AuthSettings())
  │        llm = auth.llm_config(api_key_id, user_id, model) ── 失败 → ValueError → failed，无单元结果
  ├─ 置 running（既有）
  ├─ [新] problems = ProblemStore 解析 problem_ids；缺失题目记录到 missing 集合（不 fail-fast）
  ├─ [新] harness = AlgorithmHarness(HarnessConfig(llm_config=llm, sandbox_config=SandboxConfig(),
  │                                              dataset_path=_UNUSED, strategies=[StrategyConfig(name=n)...]))
  ├─ [新] runtimes = {name: harness._prepare_strategy_runtime(sc) for ...}  ── 沙箱 preflight 失败 → failed
  ├─ _create_task_units（既有，笛卡尔积）
  ├─ TaskService(root=data/tasks/{id}) + resume 检测（既有）
  ├─ task_service.run(max_workers=1, worker=真实worker, pause_when=should_pause, on_unit_finished=落库钩子)
  │     worker(unit):
  │        problem = problem_map.get(unit.problem_id)
  │        if problem is None: raise ProblemMissing(unit.problem_id)   → unit.status=failed
  │        strategy, sandbox = runtimes[unit.strategy]
  │        result = harness._execute_problem(sc, problem, strategy, sandbox)
  │        cost, meta = harness._estimate_cost([result])
  │        result.metadata["cost_usd"], result.metadata["cost_unknown"] = cost, unknown
  │        return result                                              → unit.status=completed
  │     on_unit_finished(record, unit):   # 主线程，可触碰 db
  │        upsert EvaluationResult(by evaluation_id+problem_id+strategy_name)
  │        evaluation.spent_usd += unit.result.metadata.cost_usd
  │        evaluation.completed_count = #units status==completed
  │        evaluation.failed_count    = #units status==failed
  │        db.commit(); self.update_state(PROGRESS)
  └─ 终态映射到 evaluation.status + task_manager（既有）
```

组件职责：`run_evaluation_task` 只做编排与 DB 落库；`AlgorithmHarness` 提供执行内核（不感知 DB）；`TaskService` 提供生命周期/检查点/暂停（不感知业务）。

## 5. 详细实现设计

### 5.1 数据模型与迁移

**模型**（[api/db/models.py](file:///Users/charlesleclerc/LLM-Algorithm-Harness/api/db/models.py) `Evaluation`）新增：
```python
model: Mapped[str | None] = mapped_column(String(200))
```
DB 层可空（不破坏历史行），请求层必填（见 §5.2）。

**迁移**（新文件 `api/db/migrations/versions/<rev>_add_evaluation_model.py`）：
```python
revision = "0003"            # 或稳定 hash；down_revision 必须指向当前 head
down_revision = "3a568a0f1b04"

def upgrade() -> None:
    op.add_column("evaluations", sa.Column("model", sa.String(length=200), nullable=True))

def downgrade() -> None:
    op.drop_column("evaluations", "model")
```
SQLite 对「可空、无 server_default」的 `add_column` 原生支持，无需 `batch_alter_table`；若目标库报错再退回 `with op.batch_alter_table("evaluations") as batch_op: batch_op.add_column(...)`。

### 5.2 请求层（BREAKING）

`EvaluationCreateRequest`（[api/models.py](file:///Users/charlesleclerc/LLM-Algorithm-Harness/api/models.py)）新增必填字段：
```python
model: str = Field(..., min_length=1, description="Model name used to execute the evaluation")
```
`EvaluationService.create_evaluation` 构造 `Evaluation` 时持久化 `model=request.model`。这是 BREAKING（创建评估请求新增必填字段），已在 proposal 标注；迁移对既有行可空以不破坏历史数据。

### 5.3 执行编排改造（run_evaluation_task）

保持既有骨架（加载、验证、置 running、单元创建、resume 检测、终态映射、异常处理），仅：
1. 在「验证配置」后、「置 running」前插入 model + 凭证 fail-fast（§5.4）。
2. 在「置 running」后构造 harness + 准备 runtimes（§5.6）。
3. 用真实 worker 替换占位 worker（§5.7）。
4. 强化 `on_unit_finished` 为落库 + 成本 + 计数钩子（§5.8–5.12）。
5. `should_pause` 保持既有逻辑（§5.10），依赖真实 `spent_usd`。

### 5.4 凭证与模型解析 fail-fast

```python
if not evaluation.model:
    raise ValueError(f"Evaluation {evaluation_id} has no model configured")
from api.auth.config import AuthSettings
from api.auth.service import AuthService
auth = AuthService(AuthSettings())
try:
    llm_config = auth.llm_config(evaluation.api_key_id, evaluation.user_id, evaluation.model)
except HTTPException as exc:      # owned_key / decrypt 失败以 HTTPException 抛出
    raise ValueError(f"Credential unavailable: {exc.detail}") from None
```
- 解析发生在**任何单元执行前**；失败经既有 `except (ValueError, ...)` 分支置 `evaluation.status=failed` + `error_message`，且**不写任何 `EvaluationResult` 行**（满足 spec「凭证不可解析时评估失败」「缺少模型标识时评估失败」）。
- 把 `HTTPException` 转成 `ValueError`，避免把 HTTP 语义传播进 Celery 任务结果，也确保不触发重试（`autoretry_for` 只含 Redis/Connection 错误）。

### 5.5 题目解析与缺失处理

```python
from api.db.problem_store import ProblemStore
store = ProblemStore(<business engine/session>)   # 复用与 evaluation 同一 DB
problem_map: dict[str, DomainProblem] = {}        # DomainProblem = src.models.Problem
for pid in evaluation.problem_ids:
    row = store.get_by_problem_id(pid)            # 返回 ORM api.db.models.Problem
    if row is None:
        missing.add(pid)
        continue
    try:
        problem_map[pid] = _to_domain_problem(row)  # ORM → src.models.Problem
    except ValidationError:
        missing.add(pid)                          # 数据不完整/非法：按不可用处理，其单元单独失败
```
- **ORM→domain 转换（build 阶段发现的设计缺口，已补齐）**：`ProblemStore.get_by_problem_id` 返回 ORM `api.db.models.Problem`，而 `_execute_problem`（§5.7）消费 domain `src.models.Problem`（需 `model_copy`/`hidden_test_cases`/`unsupported_reason` 等 pydantic 成员）。故 `problem_map` 必须装 domain Problem。ORM 列与 dataset 字段 1:1（`problem_id/title/description/difficulty/tags/constraints/test_cases/source_platform/source_url`），且 domain `Problem` 的 `migrate_legacy_test_cases`(mode="before") validator 接受 `test_cases` 键（归为 `public_test_cases`，`hidden_test_cases` 为空，`migration_status="legacy_test_cases_as_public"`）。转换实现：`_to_domain_problem(row)` = 用上述列组一个 dict 后 `src.models.Problem(**data)`（等价 `ProblemLoader().load_from_dict(data)`）。所有字段均为 eagerly-loaded 列，`get_by_problem_id` 的 session 已关闭后读取仍安全（无 lazy 关系）。
- **数据限制（诚实口径）**：DB 导入题目当前只持久化 `test_cases`（→ public），无 hidden 测试；真实执行按 public 测试评测，`migration_status` 标记其来源。这是数据层限制，非代码缺陷。
- **转换失败不 fail-fast**：ORM 行缺字段/非法（如 `description` 短于 domain 的 `min_length=10`、`difficulty` 不在 `easy/medium/hard`）时 `Problem(**data)` 抛 `ValidationError`；按「不可用题目」并入 `missing` 集合，其单元在 worker 中因 `problem_map.get` 为 None 单独失败，其余题目继续。
- 缺失题目**不 fail-fast**：其单元在 worker 中因 `problem_map.get` 为 None 抛异常 → `TaskUnit.status=failed` + `unit.error=缺失原因` → `on_unit_finished` 落一条 `status="failed"` 的 `EvaluationResult`，`failed_count` 计入（满足 spec「部分题目缺失其余继续」）。
- 缺失原因文案：`f"Problem {pid} not found in problem store"`。
- `ProblemStore` 的构造入口由 builder 对齐现有用法（与 `evaluation` 同一 business engine/session factory）；worker 只读 `problem_map`，不持有 session。

### 5.6 harness 构造与策略运行时准备

```python
_UNUSED_DATASET_PATH = "db://evaluations"   # 模块级常量；HarnessConfig 必填但本路径从不被读取

strategy_configs = {name: StrategyConfig(name=name) for name in evaluation.strategy_names}
harness_config = HarnessConfig(
    llm_config=llm_config,
    sandbox_config=SandboxConfig(),          # 默认 docker 后端
    dataset_path=_UNUSED_DATASET_PATH,
    strategies=list(strategy_configs.values()),
    budget_cap_usd=None,                     # 预算由 TaskService pause_when + spent_usd 管理，不走 harness RunCostMonitor
    enable_quality_analysis=False,           # 本次范围不启用质量分析
)
harness = AlgorithmHarness(harness_config)   # __init__ 轻量，不加载数据集
runtimes = {name: harness._prepare_strategy_runtime(sc) for name, sc in strategy_configs.items()}
```
- **每策略一次** `_prepare_strategy_runtime`：建 SandboxExecutor + `health_check()` preflight + LLMClient + 策略实例，返回 `(strategy, sandbox)`，跨单元复用（镜像 [harness.py:272-275](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/harness.py#L272-L275) 的做法）。
- 未知策略名 → `_prepare_strategy_runtime` 抛 `ValueError`；沙箱 preflight 失败 → 抛 `RuntimeError`。二者都在任何单元执行前发生 → 整个评估 `failed`，无单元结果（配置/环境错误，符合 fail-fast 精神）。
- `budget_cap_usd=None`：评估的预算暂停走 DB 中心 `should_pause`（§5.10），不使用 harness 的 `RunCostMonitor`/`budget_action`，避免与 CLI 语义耦合。
- `dataset_path` 占位常量不参与 TaskService fingerprint（fingerprint 仍按既有 `{"evaluation_id": ...}` 计算，[evaluation.py:104](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py#L104)），因此不影响 resume。

### 5.7 worker 真实化（线程边界）

```python
def worker(unit: TaskUnit) -> ExecutionResult:
    problem = problem_map.get(unit.problem_id)
    if problem is None:
        raise ValueError(f"Problem {unit.problem_id} not found in problem store")
    sc = strategy_configs[unit.strategy]
    strategy, sandbox = runtimes[unit.strategy]
    result = harness._execute_problem(sc, problem, strategy, sandbox)   # 真实 LLM + hidden 沙箱 + 失败分类 + 脱敏
    cost, meta = harness._estimate_cost([result])
    result.metadata["cost_usd"] = cost
    result.metadata["cost_unknown"] = bool(meta.get("unknown_usage") or meta.get("unknown_pricing"))
    return result
```
- worker 只读 `problem_map`/`strategy_configs`/`runtimes`/`harness`，**不触碰 `db` session**（worker 在 executor 线程运行，SQLAlchemy session 非线程安全）。所有 DB 写在 `on_unit_finished`（主线程）。
- 成本在 worker 内计算并写入 `result.metadata`（`metadata` 是 dict 字段，随 `_serialize_result` 保留），避免 `on_unit_finished` 从脱敏后的 `llm_traces` 二次估算。
- `max_workers=1` → 同一时刻只有一个 worker 线程使用共享 runtime，无并发竞争。
- worker 抛异常（题目缺失、执行异常）→ `TaskService` 置 `unit.status=failed`、`unit.error=str(exc)`（[task_service.py:386-390](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py#L386-L390)）。

### 5.8 ExecutionResult → EvaluationResult 映射

在 `on_unit_finished(record, unit)` 中：
```python
if unit.status == "completed" and unit.result:
    data = unit.result                              # 已脱敏的 ExecutionResult dict
    status = data.get("status", "failed")           # success/failed/error/unsupported/budget_exhausted，均 ≤16 字符
    metrics = {
        "success": status == "success",
        "failure_category": data.get("failure_category"),
        "failure_mode": data.get("failure_mode"),
        "difficulty": data.get("difficulty"),
        "total_tokens": data.get("total_tokens", 0),
        "execution_time_seconds": data.get("execution_time_seconds", 0.0),
        "cost_usd": (data.get("metadata") or {}).get("cost_usd", 0.0),
        "cost_unknown": (data.get("metadata") or {}).get("cost_unknown", False),
        "formal_evaluable": data.get("formal_evaluable", False),
        "quality_metrics": data.get("quality_metrics"),
    }
    error_message = data.get("error_message")
    cost = float((data.get("metadata") or {}).get("cost_usd", 0.0))
else:                                               # unit.status == "failed"（worker 抛异常，含题目缺失）
    status = "failed"
    metrics = None
    error_message = unit.error
    cost = 0.0
```
- `EvaluationResult.status` 忠实存 `ExecutionResult.status`（全部 ≤ `String(16)`；`budget_exhausted` 恰好 16）；成功/失败细节在 `metrics`。
- worker 级失败（题目缺失、执行异常）→ `status="failed"`、`metrics=None`、`error_message=unit.error`。

### 5.9 成本累计与 spent_usd

```python
evaluation.spent_usd = (evaluation.spent_usd or 0.0) + cost
```
- `cost` 来自 `_estimate_cost` 的真实定价口径；无定价时 `cost=0` 且 `cost_unknown=True`（不伪造，满足新增边界场景「单元花费无可用定价时诚实计入」）。
- 只在 `on_unit_finished`（单元确证完成/失败后）累加，且 `db.commit()`；`should_pause` 读同一 `evaluation` ORM 对象的最新 `spent_usd`。

### 5.10 预算暂停

- 复用既有 `should_pause(record)`：用户请求暂停（AsyncTask.status=="paused"）或 `evaluation.budget_cap_usd is not None and evaluation.spent_usd >= evaluation.budget_cap_usd` → True（[evaluation.py:144-158](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py#L144-L158)）。
- `max_workers=1` 保证在完成单元边界严格停止；未派发单元保持 `queued`，`TaskService` 置 `record.state="paused"`（[task_service.py:346-352](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py#L346-L352)）→ 终态映射到 `evaluation.status="paused"`。
- 未设 `budget_cap_usd` → 跑完全部单元。

### 5.11 聚合计数字段（口径修正）

**关键**：`record.completed_units` 统计的是 `status in {completed, failed}` 的**已完成单元总数**（[task_service.py:392-396](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/task_service.py#L392-L396)），不等于「成功单元数」。为满足 spec「`completed_count` 与 `failed_count` 之和等于单元总数，且与实际成功/失败单元数一致」，重定义：
```python
evaluation.completed_count = sum(1 for u in record.units if u.status == "completed")
evaluation.failed_count    = sum(1 for u in record.units if u.status == "failed")
```
- 二者之和 = 已完成单元数；终态时 = `total_units`。
- Celery `PROGRESS` 的 `current` 仍用 `record.completed_units`（= completed_count + failed_count），保持进度语义。
- 这修正了既有 `on_unit_finished` 把 `completed_count = record.completed_units` 的口径（原口径会把失败单元也计入 completed_count）。

### 5.12 幂等 upsert

以 `(evaluation_id, problem_id, strategy_name)` 为幂等键：
```python
row = db.query(EvaluationResult).filter_by(
    evaluation_id=evaluation_id, problem_id=unit.problem_id, strategy_name=unit.strategy
).first()
if row is None:
    row = EvaluationResult(id=str(uuid.uuid4()), evaluation_id=evaluation_id,
                           problem_id=unit.problem_id, strategy_name=unit.strategy)
    db.add(row)
row.status = status; row.metrics = metrics; row.error_message = error_message
```
- resume 重跑同一单元不产生重复行（满足 spec「恢复继续不重复已完成单元」）。

### 5.13 resume 去重

- 复用既有 resume 检测（`existing_record.state in ("paused","failed")` → `resume=True`，[evaluation.py:112-118](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py#L112-L118)）。
- `TaskService._prepare_resume` 只重排 uncertain/running/cancelled 单元，保留 confirmed terminal（completed/failed）单元 → 已完成单元不重跑，其 `EvaluationResult` 行与已累加的 `spent_usd` 保留；计数与花费在既有基础上继续（满足 spec）。
- fingerprint 沿用既有 `config_fingerprint={"evaluation_id":...}` + `dataset_fingerprint=_hash_json(problem_ids)`，resume 时一致。

### 5.14 终态回写

保持既有映射（[evaluation.py:182-199](file:///Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py#L182-L199)）：`completed→completed`、`paused→paused`、`failed→failed`(+error_message)、`cancelled→cancelled`，并同步 `task_manager.update_task_status`。`completed` 时记录 `completed_at`（若既有未记录则补 `evaluation.completed_at = utcnow()`）。取消语义与「重启不把已入队 pending 标记失败」语义不变。

## 6. 关键取舍

| 决策 | 选择 | 理由 / 被否方案 |
|---|---|---|
| 单元执行入口 | **Option A：复用 harness 内部 `_prepare_strategy_runtime`/`_execute_problem`/`_estimate_cost`** | 完全贴合 spec（逐单元行/spent_usd/pause/resume/fail-fast），改动集中在 evaluation.py，复用已测试的执行内核。被否 Option B（委托 `harness.run`）：CLI 导向、文件型 TaskService、无 per-unit DB 钩子、budget_action 语义冲突。被否 Option C（新增公共 seam）：改动扩到 harness.py + 新增公共 API 测试，超出「仅执行体+落库」范围。 |
| 私有方法耦合 | 接受耦合 3 个下划线方法 | 同仓库、且已被 harness 自身 `_run_with_task_service` 使用（稳定）；换取零重复实现。若后续 harness 重构，evaluation 执行体需同步（记入 §9 风险）。 |
| timeout_seconds / max_concurrency | **本次都不持久化、不接入** | 用户确认。`max_concurrency` 与「预算严格暂停需 `max_workers=1`」冲突；`timeout_seconds` 无干净映射目标（`SandboxConfig.timeout_seconds` ≤60 且 per-test-case；`LLMConfig.timeout` 是请求级）。留待后续 change。 |
| 成本口径 | 复用 `_estimate_cost` 真实定价，无定价标 unknown 不伪造 | 继承 issue #15 诚实口径；预算暂停在成本未知时可能不触发，作为已知边界（§5.9 + spec 新增场景）。 |
| dataset_path | 占位常量 `db://evaluations` | `HarnessConfig` 必填但本路径从不读取；不参与 fingerprint，不影响 resume。 |

## 7. 边界条件与错误处理

- **model 缺失 / 凭证不可解析**：执行任何单元前 `failed`，无 `EvaluationResult` 行。
- **沙箱 preflight 失败 / 未知策略**：准备 runtime 时抛错 → `failed`，无单元结果。
- **部分题目缺失**：缺失单元 `failed`（附原因），其余正常执行，评估不整体中止。
- **单元执行异常**（LLM/沙箱运行期错误）：`_execute_problem` 内部已捕获并返回 `status="error"` 的 `ExecutionResult`（脱敏）→ 该单元 `completed`（worker 未抛），`EvaluationResult.status="error"`，`failed_count` 不计入（因 TaskUnit.status=="completed"）。**注意语义**：`failed_count` 统计的是「worker 抛异常/执行未能产出结果」的单元；产出了 error 结果但 worker 正常返回的单元计入 `completed_count`，其失败细节在 `EvaluationResult.status`/`metrics.failure_category`。（此口径与 spec「聚合计数」一致：completed+failed=总数。）
- **成本无定价**：`cost=0`、`cost_unknown=True`，`spent_usd` 不增长，预算暂停可能不触发（已知限制）。
- **取消**：既有 `TaskService` 取消语义不变；in-flight 单元标 uncertain，resume 时重跑。
- **worker 线程 DB 安全**：worker 不触碰 `db`；所有写在主线程 `on_unit_finished`。

## 8. 测试策略

沿用 `test_harness.py`/`test_experiment.py` 的 mock 模式，全程不触网：
- `patch("src.harness.LLMClient")`、`patch("src.harness.SandboxExecutor")`（`health_check` 返回 `(True, "")`），或 `patch` `AlgorithmHarness._execute_problem` 直接返回构造的 `ExecutionResult`（更快、更聚焦编排）。
- mock/fake `AuthService.llm_config` 返回一个合法 `LLMConfig`；fake `ProblemStore.get_by_problem_id`。
- 用临时 SQLite business DB + 迁移建表；断言 `EvaluationResult` 行、`Evaluation.completed_count/failed_count/spent_usd/status`。

覆盖用例（对齐 delta spec 场景）：
1. **全部成功**：2 策略 × 2 题目 → 4 单元 completed，`completed_count=4`，无 mock 标记，每单元一条 `EvaluationResult` 且度量非占位。
2. **凭证不可解析**：`llm_config` 抛错 → `failed`，`error_message` 说明凭证，无 `EvaluationResult` 行。
3. **model 缺失**：`evaluation.model=None` → `failed`，无 LLM 调用。
4. **部分题目缺失**：1 缺失 1 存在 → 缺失单元 `failed`（附原因）计入 `failed_count`，存在单元正常，评估不整体中止。
5. **预算暂停**：设 `budget_cap_usd`，构造 cost 使累计触顶且仍有 queued 单元 → `paused`，已完成结果与 `spent_usd` 保留。
6. **无预算**：跑完全部单元，`spent_usd` 反映真实花费。
7. **成本无定价**：`_estimate_cost` 返回 0 + unknown → `spent_usd` 不增长、`metrics.cost_unknown=True`，即使有 cap 也不暂停。
8. **resume 去重**：paused 后提高预算重发 → 仅剩余单元执行，已完成 `EvaluationResult` 不重复，`completed_count` 从暂停值继续。
9. **执行中不可恢复错误**：编排层抛错 → `failed` + error_message，关联任务状态一致。
10. **聚合口径**：部分成功部分失败 → `completed_count + failed_count == total_units`。

质量门禁（与 CI 等价，本地全绿）：`ruff check .`、`python scripts/find_missing_encoding.py`、`black --check .`、`mypy src/ --ignore-missing-imports`、`pytest -m "not online"`；所有新增文件 IO 显式 `encoding`。

## 9. 风险

- **耦合 harness 私有方法**：`_prepare_strategy_runtime`/`_execute_problem`/`_estimate_cost` 签名变化会波及本执行体。缓解：测试用 `_execute_problem` 的真实/替身路径均覆盖；在 tasks.md 标注该耦合点。
- **`_estimate_cost` 依赖 `llm_traces` 定价**：真实供应商未回传定价时 `spent_usd` 偏低、预算暂停可能不触发。缓解：`cost_unknown` 显式标记 + spec 边界场景 + 文档记录为已知限制。
- **`EvaluationResult.status` 长度**：`budget_exhausted` 恰为 16 字符，等于 `String(16)` 上限；若未来新增更长状态需扩列。缓解：映射集中在 §5.8 一处，便于调整。
- **BREAKING 请求字段**：新增必填 `model` 会破坏旧客户端。缓解：proposal 标注 BREAKING，迁移对既有行可空。

## 10. 留给 builder / 未决

- `ProblemStore` 在 worker 上下文的具体构造入口（engine/session 来源）由 builder 对齐 `api/db/problem_store.py` 现有用法确定；设计要求 worker 只读 `problem_map`，不在 worker 线程持有 session。
- 迁移 `revision` 具体取值（`"0003"` 或稳定 hash）由 builder 定，`down_revision` 必须为 `3a568a0f1b04`。
- `EvaluationResult` upsert 的查询/写入必须在 `on_unit_finished` 的主线程 `db` session 内完成。
