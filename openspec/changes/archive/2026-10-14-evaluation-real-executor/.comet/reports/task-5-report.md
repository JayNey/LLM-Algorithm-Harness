# Task 5 报告：harness 构造 + 真实 worker 工厂（诚实 cost）

- **状态**：DONE_WITH_CONCERNS（顾虑见 §9，均为下游 Task 6 接线注意项，非本任务缺陷）
- **提交哈希**：`45d3229daf4d11118c81b71f992006872b299e6b`（short `45d3229`）
- **分支**：comet/evaluation-real-executor（父提交 `ac2f9c5`）
- **测试摘要**：`tests/test_celery_tasks.py` 17 passed（本任务新增 3 个）；全量套件 `pytest -m "not online"` **1645 passed, 6 skipped**；ruff/black 全绿，mypy 仅剩既有基线错误（`api/files/parsing.py:93`）。

## 1. 改动摘要

仅改 `src/tasks/evaluation.py`（+93 行，纯新增，未改动任何既有函数体）：

1. **`_UNUSED_DATASET_PATH = "db://evaluations"`**（模块级常量）
   `HarnessConfig.dataset_path` 必填，但评估单元的题目来自题库（`problem_map`），harness 自己
   从不调用 `ProblemLoader.load()`（只有 `harness.run()` 会，本路径不走 `run()`）。常量上方有
   注释说明「运行时从不被读取」。

2. **`_build_harness(ctx, strategy_names) -> (harness, strategy_configs, runtimes)`**
   - `strategy_configs = {name: StrategyConfig(name=name) for name in strategy_names}`（保序）。
   - `HarnessConfig(llm_config=ctx.llm_config, sandbox_config=SandboxConfig(),
     dataset_path=_UNUSED_DATASET_PATH, strategies=list(strategy_configs.values()),
     budget_cap_usd=None, enable_quality_analysis=False)`。
   - `harness = AlgorithmHarness(config)`（不传 `budget_tracker`，故 `harness.budget_tracker is None`）。
   - **每策略一次**预建 runtime：`runtimes = {name: harness._prepare_strategy_runtime(sc) for ...}`，
     结果跨单元复用（避免每单元重复 docker health_check + LLMClient 构造）。
   - 沙箱 preflight 失败 / 策略名未知在此 fail-fast（`RuntimeError` / `ValueError`），
     不会拖到第一个单元执行时才暴露。

3. **`_make_worker(harness, strategy_configs, runtimes, problem_map) -> Callable[[TaskUnit], ExecutionResult]`**
   返回真实 worker 闭包（按裁定 2 统一为工厂形式，简报里的 `make_worker(...)` 是简写）：
   - 题目缺失 → `raise ValueError(f"Problem {unit.problem_id} not found in problem store")`
     （可审计文案，Task 6 的 `_record_unit_result` 失败分支会把它写进 `error_message`）。
   - `result = harness._execute_problem(strategy_config, problem, strategy, sandbox)`（复用预建 runtime）。
   - `cost, pricing_metadata = harness._estimate_cost([result])` →
     `result.metadata["cost_usd"] = cost`；
     `result.metadata["cost_unknown"] = bool(unknown_usage or unknown_pricing)`。
     无定价信息时 harness 返回 `total_cost=0.0` 且 unknown 标志置 True，故 cost 口径诚实、不伪造。
   - **闭包不捕获 db / session**（自查见 §9.1）。

4. **导入**：模块级新增 `from collections.abc import Callable, Iterable`、
   `from src.harness import AlgorithmHarness`、
   `from src.models import ExecutionResult, HarnessConfig, SandboxConfig, StrategyConfig`；
   `TYPE_CHECKING` 块新增 `from src.models import Problem as DomainProblem`
   （别名避免与既有 `api.db.models.Problem` 名称冲突）。
   已实测 `import src.tasks.evaluation`（先于 `src.harness`）无循环导入，导入耗时 ~1s，无需延迟导入。

**未改动**（严格遵守范围）：`run_evaluation_task` 主体、mock `worker()`、`_resolve_execution_context`、
`_record_unit_result`、`should_pause`；未触碰 `src/harness.py`、`src/models.py`、`src/task_service.py`、
`api/**`、迁移文件。**未接线**（接线是 Task 6）。

## 2. 新增测试

文件：`tests/test_celery_tasks.py`（沿用既有约定，未新建 `test_evaluation_task.py`）

- fixture `eval_ctx`：真实 `_EvalContext`，`llm_config` 为占位 `LLMConfig(provider="openai",
  api_key=SecretStr("sk-placeholder"), model="test-model")`；`problem_map={"p1": Problem(...)}`
  （真实 domain Problem，含 1 条 public + 1 条 hidden 用例，满足 Problem 校验器）；`missing_problems=set()`。
- fixture `harness_ctx`：调用**真实** `_build_harness(eval_ctx, ["vanilla", "chain_of_thought"])`，
  但三重隔离：`patch.object(AlgorithmHarness, "_prepare_strategy_runtime", Mock(return_value=(object(), object())))`
  + `patch("src.harness.SandboxExecutor", side_effect=AssertionError(...))`
  + `patch("src.harness.LLMClient", side_effect=AssertionError(...))`（后两者是护栏，一旦被触碰即失败）。
  返回 `((harness, strategy_configs, runtimes), prepare_mock)`。
- `TestBuildHarness::test_build_harness_prepares_runtime_once_per_strategy`：断言
  `isinstance(harness, AlgorithmHarness)`、`config.llm_config is ctx.llm_config`、
  `config.dataset_path == _UNUSED_DATASET_PATH`、`budget_cap_usd is None`、
  `enable_quality_analysis is False`、`budget_tracker is None`、strategy_configs 键与 `name` 一致、
  `config.strategies == list(strategy_configs.values())`、
  **`prepare.call_count == 策略数(2)` 且逐次传入对应 StrategyConfig**、
  `runtimes` 键集合一致且值为预建哨兵（同一对象）。
- `TestMakeWorker::test_worker_returns_real_result_with_cost`：monkeypatch
  `harness._execute_problem`（返回真实 `ExecutionResult(status="success")` 并记录入参）与
  `harness._estimate_cost`（固定 `(0.02, {"unknown_usage": False, "unknown_pricing": False})`）；
  断言 worker 返回 `ExecutionResult`、`status/problem_id/strategy` 正确、
  `metadata["cost_usd"] == 0.02`、`metadata["cost_unknown"] is False`；
  并断言传给 `_execute_problem` 的是**复用的**预建 runtime（`args[0] is strategy_configs["vanilla"]`、
  `args[1] is problem_map["p1"]`、`args[2:] == runtimes["vanilla"]`）。
- `TestMakeWorker::test_worker_missing_problem_raises`：`problem_id="ghost"` →
  `pytest.raises(ValueError, match="not found in problem store")`。
- 顶部导入追加：`SecretStr`、`AlgorithmHarness`、`ExecutionResult`、`LLMConfig`、`Problem`。

按裁定 1，**未写**预算暂停测试（`test_budget_pause_stops_scheduling`），**未改动** `should_pause`；
该行为由 Task 6 的 `test_run_evaluation_task_budget_pause` 覆盖。

## 3. RED（先失败，特性缺失）

命令：
```
python3 -m pytest tests/test_celery_tasks.py -k "worker_returns_real or worker_missing_problem or build_harness" -v --no-cov
```

失败摘要（3 个测试全部因**目标特性不存在**而失败）：
```
tests/test_celery_tasks.py:474: in harness_ctx
    from src.tasks.evaluation import _build_harness
E   ImportError: cannot import name '_build_harness' from 'src.tasks.evaluation'
    (/Users/charlesleclerc/LLM-Algorithm-Harness/src/tasks/evaluation.py)
================= 14 deselected, 1 warning, 3 errors in 1.35s ==================
```

RED 过程的两轮修正（保证「失败原因是特性缺失，而非测试自身错误」）：
1. 首轮 fixture 构造 `Problem` 抛 `ValidationError: At least one public, feedback, or hidden test
   case is required` → 补 public/hidden 用例。
2. 修正后出现 `PytestCollectionWarning: cannot collect test class 'TestCase'`（pytest 误采集
   `src.models.TestCase`）→ 改用 dict 字面量构造用例、移除 `TestCase` 导入，警告消失。
   之后仅剩既有 `api/config.py` pydantic 弃用警告（与本任务无关）。

## 4. GREEN

```
python3 -m pytest tests/test_celery_tasks.py -k "worker_returns_real or worker_missing_problem or build_harness" -v --no-cov
tests/test_celery_tasks.py::TestBuildHarness::test_build_harness_prepares_runtime_once_per_strategy PASSED [ 33%]
tests/test_celery_tasks.py::TestMakeWorker::test_worker_returns_real_result_with_cost PASSED [ 66%]
tests/test_celery_tasks.py::TestMakeWorker::test_worker_missing_problem_raises PASSED [100%]
================= 3 passed, 14 deselected, 1 warning in 1.30s ==================
```

## 5. 回归

- 目标文件：`python3 -m pytest tests/test_celery_tasks.py -q --no-cov` → **17 passed, 1 warning**（原 14 + 新 3）。
- 全量套件（TDD 技能要求跑项目套件，不止本文件）：
  `python3 -m pytest -q --no-cov -m "not online" -p no:randomly` → **1645 passed, 6 skipped, 113 warnings in 147.89s**。
  无失败、无错误；warnings 均为既有（matplotlib legend、scipy 精度、SQLAlchemy `Result.tuples()` 弃用、
  pydantic class-based config 弃用），与本改动无关。

## 6. 门禁

| 命令 | 结果 |
| --- | --- |
| `ruff check src/tasks/evaluation.py tests/test_celery_tasks.py` | All checks passed!（exit 0） |
| `black --check src/tasks/evaluation.py tests/test_celery_tasks.py` | 2 files would be left unchanged（exit 0） |
| `mypy src/ --ignore-missing-imports` | `Found 1 error in 1 file (checked 96 source files)` — 仅既有基线 `api/files/parsing.py:93: Class cannot subclass "SafeLoader"`，**无新增错误** |

black 说明：首次 `black --check` 报 `tests/test_celery_tasks.py` 需重排（我手写的多行 assert），
按 `black --diff` 输出手工改为单行后复查通过；未对文件执行整体 `black <file>`（避免产生无关改动）。
已验证 HEAD 版本两文件本就 black-clean，故当前差异全部由本任务引入并已修正。

## 7. 变更文件与 diff 规模

```
 src/tasks/evaluation.py    |  93 +++++++++++++++++++++++++++++++
 tests/test_celery_tasks.py | 135 +++++++++++++++++++++++++++++++++++++++++++++
 2 files changed, 228 insertions(+)
```
纯新增（0 删除、0 修改既有行）。生产代码 93 行（其中约 60 行是中文 docstring/注释），测试 135 行。

## 8. 风险信号自报（逐条对照）

| 风险信号 | 命中 | 说明 |
| --- | --- | --- |
| 跨模块协调 | **命中（轻）** | 新代码消费 `src.harness.AlgorithmHarness` 的三个内部方法（`_prepare_strategy_runtime` / `_execute_problem` / `_estimate_cost`，下划线私有 API）。若 harness 侧重构这些方法签名，评估链路会静默断裂——已在测试中固定其调用契约（入参顺序、返回结构）。本任务未修改 harness。 |
| 安全敏感面 | **命中（轻）** | `HarnessConfig.llm_config` 携带真实 api_key（`SecretStr`）。当前只在 `_build_harness` 内传递给 harness，`AlgorithmHarness.__init__` 会 `logger.info("harness_initialized", config=config.redacted_dict())`（已 redact）。worker 不把 llm_config/api_key 写入 `result.metadata`。 |
| 并发 / 锁 / 共享状态 | **命中** | runtime 预建后被**所有单元共享**：同一策略的 `strategy` 实例与 `SandboxExecutor` 在 TaskService 的 executor 线程间复用。`max_workers=1`（既有编排）时安全；若 Task 6+ 提高并发，需确认策略实例/SandboxExecutor 的线程安全性（`AlgorithmHarness` 自身有 `_results_lock`，但我们不走它的聚合路径）。另：worker 闭包严格不捕获 db/session（见 §9.1）。 |
| 数据或 schema 迁移 | 未命中 | 无迁移、无模型字段变更。 |
| 公共 API 契约变更 | 未命中 | 新增两个模块级私有函数（`_` 前缀）+ 一个私有常量；HTTP API、Celery 任务签名、`run_evaluation_task` 返回结构均未变。 |
| diff > 200 行 | **命中** | 228 insertions（生产 93 + 测试 135）。纯新增、无既有行改写，review 面集中。 |

## 9. 顾虑（Concerns）

### 9.1 worker 是否引用 db —— 自查结论：**未引用（已用字节码验证）**
```
freevars: ('harness', 'problem_map', 'runtimes', 'strategy_configs')
co_names: ('get', 'problem_id', 'ValueError', 'strategy', '_execute_problem', '_estimate_cost', 'metadata', 'bool')
```
闭包自由变量只有 4 个（harness / 策略配置 / runtime / 只读题目映射），无 `db`、无 `Session`、
无 `evaluation`、无 `task_manager`、无 `self`（Celery task）。源码中亦无 `Session` 字样。
`_make_worker` 的 docstring 已把「绝不捕获 db 会话」写成显式约束，防止 Task 6 接线时误加。

### 9.2 `problem_map` 的元素类型（**Task 6 必须处理**）
`_EvalContext.problem_map` 由 Task 3 的 `_resolve_execution_context` 用
`ProblemStore.get_by_problem_id()` 填充，返回的是 **`api.db.models.Problem`（SQLAlchemy ORM 行）**；
而 `harness._execute_problem` 期望 **`src.models.Problem`（pydantic domain 模型，会调用
`problem.model_copy(...)`、读 `hidden_test_cases` / `unsupported_reason` / `formal_evaluable`）**。
两者当前**不兼容**：直接接线会在第一个单元抛 `AttributeError`。
- 本任务按裁定未改 `_resolve_execution_context`（禁改范围），故 `_make_worker` 的注解写作
  `dict[str, DomainProblem]`（= `src.models.Problem`），即**以实现方（harness）契约为准**。
- 需要在 Task 6（或补一个 Task 3 的后续小步）加一层 ORM→domain 转换（并保证在 session 关闭前
  完成字段读取，否则 detached instance 会触发 `DetachedInstanceError`）。这是本任务留给下游的**唯一硬阻塞项**。
- 我的测试用真实 `src.models.Problem` 构造 `problem_map`，正是把该契约钉死，避免 Task 6 误传 ORM 行。

### 9.3 `cost_unknown is True` 分支未被单测覆盖（按裁定收窄）
裁定 1 限定本任务只写 3 个测试，故 `unknown_usage/unknown_pricing=True → cost_unknown=True,
cost_usd=0.0`（诚实口径）这条分支只由实现保证、未单独断言。建议 Task 6 的集成测试
（或后续补齐）覆盖「无定价 → spent_usd 不增且 cost_unknown=True」，以免静默回归成伪造花费。

### 9.4 runtime 预建的失败语义
`_build_harness` 在预建阶段 fail-fast：任一策略的 docker preflight 失败会抛 `RuntimeError`，
整个评估在**执行任何单元前**失败（而非跳过该策略）。这符合「诚实、不静默降级」的取向，
但 Task 6 接线时要把该异常归入既有 `except Exception` 分支（置 `failed` + 写 `error_message`），
不要让它变成 Celery 无限重试（`autoretry_for` 只含 Redis/Connection 错误，`RuntimeError` 不在其中，符合预期）。

### 9.5 `_prepare_strategy_runtime` 使用私有 API
调用三个下划线方法是简报与裁定明确指定的路径（避免走 `harness.run()` 的数据集加载/报告聚合）。
若上游把它们改名，本模块与测试会立即失败（不会静默），属可接受的耦合。
