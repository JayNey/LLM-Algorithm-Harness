---
change: evaluation-results-api
design-doc: docs/superpowers/specs/2026-10-17-evaluation-results-api-design.md
base-ref: ddcb7ade01c2a4205c94a3331c4ccefc46c17fbe
---

# 评估结果查询 API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为已落库评估提供 issue #155 的查询、统计、对比、可视化、失败分析和报告 API。

**Architecture:** `EvaluationResultsService` 从 `evaluations`、`evaluation_results`、`problems` 读时聚合。路由只做认证和 `ApiResponse`。新写入只在 `metrics` 中增加 `iterations` 整数。

**Tech Stack:** FastAPI、SQLAlchemy、现有 `ApiResponse` / `PaginatedData`、`capability_profiler`、`normalize_message`、`MarkdownGenerator`、`HTMLGenerator`、`ChartGenerator`。

**Spec:** `docs/superpowers/specs/2026-10-17-evaluation-results-api-design.md`

## Global Constraints

- 路径按 issue #155「API端点设计」，JSON 放在 `ApiResponse.data`。
- 成功口径是结果行 `status == "success"`。
- `cost_unknown` 不计入美元合计，响应标出未知数量。
- `metrics.iterations` 缺失时迭代统计为未知，不得写成 0 或 1。
- 新写入的 `iterations` 是轨迹长度；没有轨迹列表时为 0。不保存生成代码或沙箱输出。
- 他人资源返回 404。列表默认 20 条，最大 100 条。
- 详情的策略汇总覆盖全部单元并含 `avg_execution_time`；题目只返回当前页。
- 雷达维度来自 `capability_profiler.ALL_DIMENSIONS`，映射为 `dimensions` / `series` / `problem_counts`。
- 失败汇总计数已保存的 `failure_mode`，查询时不调用 `classify_failure_mode`。
- CSV 对未落库测试计数和缺失 `iterations` 留空。
- 不连接真实 LLM 或 Redis。不新建业务表。

---

### Task 1: 写入迭代次数

- [x] Task 1: 写入迭代次数

对应 `tasks.md` 1.1。

**Files:**
- Modify: `src/tasks/evaluation.py`（`_record_unit_result`）
- Test: `tests/test_evaluation_result_iterations.py`

**Interfaces:**
- Consumes: `unit.result["iterations"]` 列表
- Produces: `EvaluationResult.metrics["iterations"]: int`

- [ ] **Step 1: Write the failing test**

```python
import uuid

from api.db.models import Base, Evaluation, EvaluationResult
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.tasks.evaluation import _record_unit_result


class _Unit:
    def __init__(self, status, result, problem_id="two-sum", strategy="vanilla", error=None):
        self.status = status
        self.result = result
        self.problem_id = problem_id
        self.strategy = strategy
        self.error = error


def test_record_unit_result_stores_iteration_count_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            user_id="owner",
            run_id="run-1",
            status="running",
            strategy_names=["vanilla"],
            problem_ids=["two-sum"],
        )
        db.add(evaluation)
        db.flush()
        _record_unit_result(
            db,
            evaluation,
            _Unit(
                "completed",
                {
                    "status": "success",
                    "iterations": [{"code": "secret"}, {"code": "still-secret"}],
                    "generated_code": "print(1)",
                    "total_tokens": 10,
                    "execution_time_seconds": 1.5,
                    "metadata": {"cost_usd": 0.1, "cost_unknown": False},
                },
            ),
        )
        db.commit()
        row = db.query(EvaluationResult).one()
        assert row.metrics["iterations"] == 2
        assert "generated_code" not in row.metrics
        assert "secret" not in str(row.metrics)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_evaluation_result_iterations.py -q --no-cov`

Expected: FAIL，`metrics` 中没有 `iterations` 或断言失败。

- [ ] **Step 3: Write minimal implementation**

在 `src/tasks/evaluation.py` 的 completed 分支 metrics 字典加入：

```python
iterations = data.get("iterations")
metrics["iterations"] = len(iterations) if isinstance(iterations, list) else 0
```

不要把 `iterations` 或 `generated_code` 放进 metrics。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_evaluation_result_iterations.py -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_evaluation_result_iterations.py src/tasks/evaluation.py
git commit -m "feat: persist evaluation iteration counts"
```

### Task 2: 查询服务的归属、分页和过滤

- [x] Task 2: 查询服务的归属、分页和过滤

对应 `tasks.md` 1.2。

**Files:**
- Create: `api/services/evaluation_results_service.py`
- Test: `tests/test_evaluation_results_service.py`

**Interfaces:**
- Consumes: `Evaluation`、`EvaluationResult`、`Problem`
- Produces:
  - `EvaluationResultsService(database_url: str | None = None)`
  - `detail(owner_id: str, run_id: str, limit: int = 20, offset: int = 0) -> dict`
  - `list_runs(owner_id: str, *, strategy: str | None, difficulty: str | None, tag: str | None, status: str | None, limit: int, offset: int, sort: str, order: str) -> tuple[list[dict], int]`
  - `problem_history(owner_id: str, problem_id: str, *, status: str | None, limit: int, offset: int) -> tuple[list[dict], int]`
  - 内部 `aggregate(rows) -> dict`，供后续任务复用

- [ ] **Step 1: Write the failing test**

```python
import uuid
from datetime import datetime

import pytest
from api.db.models import Base, Evaluation, EvaluationResult, Problem
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.services.evaluation_results_service import EvaluationResultsService


def _seed(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Problem(id="p1", problem_id="two-sum", title="Two Sum", difficulty="easy", tags=["array"]))
        owned = Evaluation(
            id="eval-own",
            user_id="owner",
            run_id="run-own",
            status="completed",
            strategy_names=["vanilla", "retry"],
            problem_ids=["two-sum"],
            model="gpt-test",
            created_at=datetime(2026, 10, 1, 0, 0, 0),
            completed_at=datetime(2026, 10, 1, 1, 0, 0),
        )
        other = Evaluation(
            id="eval-other",
            user_id="other",
            run_id="run-other",
            status="completed",
            strategy_names=["vanilla"],
            problem_ids=["two-sum"],
            model="gpt-test",
        )
        db.add_all([owned, other])
        db.add_all([
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id="eval-own",
                problem_id="two-sum",
                strategy_name="vanilla",
                status="success",
                metrics={"success": True, "total_tokens": 10, "execution_time_seconds": 1.0, "cost_usd": 0.2, "cost_unknown": False, "difficulty": "easy", "iterations": 1},
            ),
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id="eval-own",
                problem_id="two-sum",
                strategy_name="retry",
                status="failed",
                metrics={"success": False, "total_tokens": 30, "execution_time_seconds": 3.0, "cost_usd": 9.0, "cost_unknown": True, "difficulty": "easy"},
                error_message="boom",
            ),
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id="eval-other",
                problem_id="two-sum",
                strategy_name="vanilla",
                status="success",
                metrics={"iterations": 1, "total_tokens": 1, "cost_usd": 1, "cost_unknown": False},
            ),
        ])
        db.commit()
    return url


def test_detail_scopes_to_owner_and_keeps_full_strategy_summary(tmp_path):
    service = EvaluationResultsService(_seed(tmp_path))
    with pytest.raises(ValueError, match="not found"):
        service.detail("owner", "eval-other")
    data = service.detail("owner", "run-own", limit=1, offset=0)
    vanilla = next(item for item in data["strategies"] if item["name"] == "vanilla")
    assert vanilla["success_rate"] == 1.0
    assert vanilla["solved_problems"] == 1
    assert vanilla["total_problems"] == 1
    assert vanilla["estimated_cost_usd"] == 0.2
    assert vanilla["avg_execution_time"] == 1.0
    retry = next(item for item in data["strategies"] if item["name"] == "retry")
    assert retry["estimated_cost_usd"] == 0.0
    assert retry["unknown_cost_count"] == 1
    assert len(data["strategies"]) == 2
    assert data["problems"]["total"] == 2
    assert len(data["problems"]["items"]) == 1
    history, total = service.problem_history("owner", "two-sum", status=None, limit=20, offset=0)
    assert total == 2
    assert all(item["run_id"] == "run-own" for item in history)
    runs, run_total = service.list_runs(
        "owner", strategy=None, difficulty=None, tag="array", status="completed",
        limit=20, offset=0, sort="completed_at", order="desc",
    )
    assert run_total == 1
    assert runs[0]["run_id"] == "run-own"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_evaluation_results_service.py::test_detail_scopes_to_owner_and_keeps_full_strategy_summary -q --no-cov`

Expected: FAIL，`EvaluationResultsService` 不存在。

- [ ] **Step 3: Write minimal implementation**

服务构造与 `EvaluationService` 相同：`make_engine`、`run_migrations`、`make_session_factory`。`resolve` 在 `user_id == owner_id` 下先按 `Evaluation.id` 再按 `Evaluation.run_id` 查找，找不到抛 `ValueError("Evaluation not found")`。

`aggregate` 按 `strategy_name` 分组：

```python
def _num(metrics: dict | None, key: str) -> float | None:
    if not metrics or key not in metrics or metrics[key] is None:
        return None
    return float(metrics[key])


def aggregate(rows: list[EvaluationResult]) -> list[dict]:
    grouped: dict[str, list[EvaluationResult]] = {}
    for row in rows:
        grouped.setdefault(row.strategy_name, []).append(row)
    strategies = []
    for name, items in grouped.items():
        solved = sum(1 for row in items if row.status == "success")
        known_cost = [
            float((row.metrics or {}).get("cost_usd") or 0)
            for row in items
            if not (row.metrics or {}).get("cost_unknown")
        ]
        times = [value for row in items if (value := _num(row.metrics, "execution_time_seconds")) is not None]
        tokens = [value for row in items if (value := _num(row.metrics, "total_tokens")) is not None]
        strategies.append({
            "name": name,
            "success_rate": solved / len(items) if items else 0.0,
            "total_problems": len(items),
            "solved_problems": solved,
            "avg_tokens": (sum(tokens) / len(tokens)) if tokens else 0.0,
            "estimated_cost_usd": sum(known_cost),
            "unknown_cost_count": sum(1 for row in items if (row.metrics or {}).get("cost_unknown")),
            "avg_execution_time": (sum(times) / len(times)) if times else 0.0,
            "by_difficulty": _by_difficulty(items),
        })
    return strategies
```

`_by_difficulty` 用 `metrics["difficulty"]`，形如 `{"easy": {"success_rate": float, "solved": int, "total": int}}`。

`detail` 的 `problems.items` 在分页后映射为：

```python
{
    "problem_id": row.problem_id,
    "strategy": row.strategy_name,
    "status": row.status,
    "iterations": None if row.metrics is None or "iterations" not in row.metrics else row.metrics["iterations"],
    "tokens": (row.metrics or {}).get("total_tokens"),
    "execution_time": (row.metrics or {}).get("execution_time_seconds"),
}
```

`strategies` 使用未分页的全部行。`list_runs` 断言前那次 `detail(..., limit=1)` 仍返回两个策略。

`list_runs` 只返回该用户的评估。标签、策略、难度用 EXISTS 子查询保留至少一条匹配单元的运行。`status` 过滤 `Evaluation.status`。排序只接受 `completed_at` 与 `created_at`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_evaluation_results_service.py -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py tests/test_evaluation_results_service.py
git commit -m "feat: aggregate stored evaluation results for their owner"
```

### Task 3: 结果查询路由

- [x] Task 3: 结果查询路由

对应 `tasks.md` 2.1。

**Files:**
- Create: `api/routes/evaluation_results.py`
- Modify: `api/main.py`、`api/routes/__init__.py`、`api/services/__init__.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Consumes: `EvaluationResultsService.detail`、`list_runs`、`problem_history`
- Produces: `GET /api/v1/results`、`GET /api/v1/results/problems/{problem_id}`、`GET /api/v1/results/{run_id}`

- [ ] **Step 1: Write the failing test**

按 `tests/test_api_experiment_benchmark.py` 的 `auth_config` 和注册登录方式创建 `TestClient`。在业务库插入 Task 2 的两条评估。断言：

```python
def test_results_api_hides_other_users_and_paginates_problems(client, owner_headers):
    own = client.get("/api/v1/results/run-own", headers=owner_headers, params={"limit": 1})
    assert own.status_code == 200
    body = own.json()
    assert body["success"] is True
    assert body["data"]["strategies"][0]["total_problems"] >= 1
    assert body["data"]["problems"]["total"] == 2
    assert len(body["data"]["problems"]["items"]) == 1
    missing = client.get("/api/v1/results/eval-other", headers=owner_headers)
    assert missing.status_code == 404
    listed = client.get("/api/v1/results", headers=owner_headers, params={"tag": "array"})
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["run_id"] == "run-own"
    anon = client.get("/api/v1/results/run-own")
    assert anon.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_results_api_hides_other_users_and_paginates_problems -q --no-cov`

Expected: FAIL，404 因为路由不存在，或不是预期的 401。

- [ ] **Step 3: Write minimal implementation**

`create_app` 中 `app.state.evaluation_results = EvaluationResultsService(database_url)`。路由前缀 `/api/v1`。`limit` 不在 1–100 时用 20，`offset < 0` 时用 0。`not found` 的 `ValueError` 转 404。静态路径 `/results/problems/{problem_id}` 写在 `/results/{run_id}` 之前。

```python
@router.get("/results/problems/{problem_id}")
def problem_history(...) -> ApiResponse[PaginatedData[dict]]:
    items, total = service.problem_history(...)
    data = PaginatedData(items=items, total=total, limit=limit, offset=offset, has_more=offset + limit < total)
    return ApiResponse(success=True, data=data, message="Problem results retrieved")
```

详情和列表同样包 `ApiResponse`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_results_api_hides_other_users_and_paginates_problems -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/routes/evaluation_results.py api/main.py api/routes/__init__.py api/services/__init__.py tests/test_api_evaluation_results.py
git commit -m "feat: expose owner-scoped evaluation result queries"
```

### Task 4: 统计端点

- [x] Task 4: 统计端点

对应 `tasks.md` 2.2。

**Files:**
- Modify: `api/services/evaluation_results_service.py`、`api/routes/evaluation_results.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Produces:
  - `success_rate(owner_id, *, run_id=None, strategy=None, difficulty=None, tag=None) -> dict`
  - `tokens(...) -> dict`
  - `iterations(...) -> dict`
  - `failure_modes(...) -> dict`

- [ ] **Step 1: Write the failing test**

夹具使用 3 个成功单元和 1 个失败单元，其中一个成功单元 `cost_unknown=True` 且 `cost_usd=9`，另一个 `cost_usd=0.2`。一条历史行不写 `iterations`。

```python
def test_analytics_match_stored_rows(client, owner_headers):
    rate = client.get("/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-own"})
    assert rate.status_code == 200
    assert rate.json()["data"]["success_rate"] == 0.75
    assert rate.json()["data"]["solved"] == 3
    assert rate.json()["data"]["total"] == 4
    tokens = client.get("/api/v1/analytics/tokens", headers=owner_headers, params={"run_id": "run-own"})
    assert tokens.json()["data"]["estimated_cost_usd"] == 0.2
    assert tokens.json()["data"]["unknown_cost_count"] == 1
    iterations = client.get("/api/v1/analytics/iterations", headers=owner_headers, params={"run_id": "run-own"})
    payload = iterations.json()["data"]
    assert payload["unknown_count"] == 1
    assert payload["known_count"] == 3
    assert all(item["iterations"] != 0 for item in payload["distribution"])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_analytics_match_stored_rows -q --no-cov`

Expected: FAIL，路由 404。

- [ ] **Step 3: Write minimal implementation**

不传 `run_id` 时只取该用户 `status == "completed"` 的评估。传入时调用 `resolve`。`iterations` 返回：

```python
{
    "known_count": len(known),
    "unknown_count": unknown,
    "average": (sum(known) / len(known)) if known else None,
    "distribution": [{"iterations": value, "count": count} for value, count in sorted(Counter(known).items())],
}
```

`failure_modes` 对非成功行的 `metrics["failure_mode"]` 计数，键缺失时记为 `"unknown"`。`success_rate` 同时返回 `avg_execution_time`。四个路由共用过滤参数 `run_id`、`strategy`、`difficulty`、`tag`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_analytics_match_stored_rows -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py api/routes/evaluation_results.py tests/test_api_evaluation_results.py
git commit -m "feat: add evaluation analytics over stored rows"
```

### Task 5: 对比端点

- [x] Task 5: 对比端点

对应 `tasks.md` 2.3。

**Files:**
- Modify: `api/services/evaluation_results_service.py`、`api/routes/evaluation_results.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Consumes: `ABTestService.results(test_id, owner_id)`
- Produces: `compare_strategies`、`compare_models`、`compare_history`

- [ ] **Step 1: Write the failing test**

```python
def test_compare_matches_detail_and_empty_history(client, owner_headers):
    detail = client.get("/api/v1/results/run-own", headers=owner_headers).json()["data"]
    compared = client.get("/api/v1/compare/strategies", headers=owner_headers, params={"run_id": "run-own"})
    assert compared.status_code == 200
    by_name = {item["name"]: item for item in detail["strategies"]}
    for item in compared.json()["data"]["strategies"]:
        assert item["success_rate"] == by_name[item["name"]]["success_rate"]
        assert item["solved_problems"] == by_name[item["name"]]["solved_problems"]
        assert item["estimated_cost_usd"] == by_name[item["name"]]["estimated_cost_usd"]
    history = client.get("/api/v1/compare/history", headers=owner_headers, params={"run_id": "run-own"})
    assert history.status_code == 200
    assert history.json()["data"]["series"] == []
    missing = client.get("/api/v1/compare/ab-test/missing", headers=owner_headers)
    assert missing.status_code == 404
```

再插入第二个已完成评估，模型不同、策略集合相同，断言 `/compare/models` 分组后的成功率与各自详情一致。历史对比只在模型与 `strategy_names` 集合都相同且已完成时返回点，并排除当前 `run_id`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_compare_matches_detail_and_empty_history -q --no-cov`

Expected: FAIL，路由 404。

- [ ] **Step 3: Write minimal implementation**

`/compare/strategies` 没有 `run_id` 时返回 400。`/compare/ab-test/{test_id}` 调用已挂在 `app.state.ab_tests` 的 `results`，异常转换与 `api/routes/ab_tests.py` 的 `call` 相同。`compare_history` 没有其他运行时返回 `{"series": []}`，HTTP 200。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_compare_matches_detail_and_empty_history -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py api/routes/evaluation_results.py tests/test_api_evaluation_results.py
git commit -m "feat: compare stored evaluation strategies and models"
```

### Task 6: 可视化 JSON

- [x] Task 6: 可视化 JSON

对应 `tasks.md` 3.1。

**Files:**
- Modify: `api/services/evaluation_results_service.py`、`api/routes/evaluation_results.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Consumes: `calculate_dimension_scores`、`format_dimension_scores_for_radar`、`get_dimension_problem_counts`、`BenchmarkRun`
- Produces: 五个 `/api/v1/visualizations/*` 方法

- [ ] **Step 1: Write the failing test**

```python
from src.reporting.capability_profiler import ALL_DIMENSIONS


def test_radar_and_empty_learning_curve(client, owner_headers):
    radar = client.get("/api/v1/visualizations/capability-radar", headers=owner_headers, params={"run_id": "run-own"})
    assert radar.status_code == 200
    data = radar.json()["data"]
    assert data["dimensions"] == ALL_DIMENSIONS
    assert data["series"][0]["name"] == "gpt-test"
    assert all(0 <= score <= 100 for score in data["series"][0]["data"])
    assert set(data["problem_counts"]) == set(ALL_DIMENSIONS)
    curve = client.get("/api/v1/visualizations/learning-curve", headers=owner_headers)
    assert curve.status_code == 200
    assert curve.json()["data"]["series"] == []
```

另断言 `success-rate-chart` 的策略成功率等于详情，`token-chart` 每条线的点是该策略各题 token，`cost-accuracy` 的成本等于 `estimated_cost_usd`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_radar_and_empty_learning_curve -q --no-cov`

Expected: FAIL，路由 404。

- [ ] **Step 3: Write minimal implementation**

雷达输入使用 dict，`model` 取评估的 `model`，`status` 取结果行。映射：

```python
formatted = format_dimension_scores_for_radar(scores)
return {
    "dimensions": formatted["dimension_names"],
    "series": [
        {"name": name, "data": values}
        for name, values in formatted["model_scores"].items()
    ],
    "problem_counts": get_dimension_problem_counts(problem_dicts),
}
```

学习曲线查询 `BenchmarkRun.user_id == owner` 且 `status == "completed"`，按 `completed_at`、`id` 排序。点包含 `suite_id`、`timestamp`、`model`、`accuracy`、`cost_usd`。可选 `suite_id` 过滤。没有行时 `series` 为 `[]`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_radar_and_empty_learning_curve -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py api/routes/evaluation_results.py tests/test_api_evaluation_results.py
git commit -m "feat: return evaluation chart data from stored results"
```

### Task 7: 失败分析

- [x] Task 7: 失败分析

对应 `tasks.md` 3.2。

**Files:**
- Modify: `api/services/evaluation_results_service.py`、`api/routes/evaluation_results.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Consumes: `src.error_analysis.normalize_message`
- Produces: `failure_summary`、`failures_by_tag`、`failure_cases`

- [ ] **Step 1: Write the failing test**

```python
def test_failure_summary_keeps_stored_mode(client, owner_headers):
    summary = client.get("/api/v1/failures/summary/run-own", headers=owner_headers)
    assert summary.status_code == 200
    assert summary.json()["data"]["modes"]["logic_error"] == 1
    assert summary.json()["data"]["clusters"][0]["pattern"]
    cases = client.get("/api/v1/failures/cases/run-own", headers=owner_headers)
    assert all(item["status"] != "success" for item in cases.json()["data"]["items"])
    assert cases.json()["data"]["items"][0]["error_message"] == "boom 42"
    tags = client.get("/api/v1/failures/by-tag", headers=owner_headers, params={"run_id": "run-own"})
    assert "array" in tags.json()["data"]["tags"]
```

夹具里的失败行 `failure_mode` 为 `logic_error`，`error_message` 为 `"boom 42"`。断言聚类 pattern 来自 `normalize_message("boom 42")`，且响应里的 mode 仍是 `logic_error`。

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_failure_summary_keeps_stored_mode -q --no-cov`

Expected: FAIL，路由 404。

- [ ] **Step 3: Write minimal implementation**

```python
from collections import Counter
from src.error_analysis import normalize_message

modes = Counter(
    (row.metrics or {}).get("failure_mode") or "unknown"
    for row in rows
    if row.status != "success"
)
clusters = Counter(
    normalize_message(row.error_message)
    for row in rows
    if row.status != "success" and row.error_message
)
```

`failures/by-tag` 按 `problems.tags` 计算每个标签的 `success_rate`、`solved`、`total`。不要调用 `classify_failure_mode` 或 `analyze_results`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_failure_summary_keeps_stored_mode -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py api/routes/evaluation_results.py tests/test_api_evaluation_results.py
git commit -m "feat: summarize stored evaluation failures"
```

### Task 8: 报告导出

- [x] Task 8: 报告导出

对应 `tasks.md` 3.3。

**Files:**
- Modify: `api/services/evaluation_results_service.py`、`api/routes/evaluation_results.py`
- Test: `tests/test_api_evaluation_results.py`

**Interfaces:**
- Consumes: `MarkdownGenerator.generate`、`HTMLGenerator.generate`
- Produces: `report_markdown`、`report_csv`、`report_html`，返回 `str`

- [ ] **Step 1: Write the failing test**

```python
def test_reports_match_json_and_blank_missing_csv_fields(client, owner_headers):
    stats = client.get("/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-own"}).json()["data"]
    markdown = client.get("/api/v1/reports/markdown/run-own", headers=owner_headers)
    assert markdown.status_code == 200
    assert "text/markdown" in markdown.headers["content-type"]
    assert f"{stats['success_rate'] * 100:.1f}%" in markdown.text
    assert str(stats["solved"]) in markdown.text
    csv_response = client.get("/api/v1/reports/csv/run-own", headers=owner_headers)
    assert "text/csv" in csv_response.headers["content-type"]
    rows = list(csv.DictReader(io.StringIO(csv_response.text.lstrip("\ufeff"))))
    historical = next(row for row in rows if row["problem_id"] == "old-problem")
    assert historical["iterations"] == ""
    assert historical["total_tests"] == ""
    foreign = client.get("/api/v1/reports/csv/eval-other", headers=owner_headers)
    assert foreign.status_code == 404
    assert "text/csv" not in foreign.headers.get("content-type", "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_reports_match_json_and_blank_missing_csv_fields -q --no-cov`

Expected: FAIL，路由 404。

- [ ] **Step 3: Write minimal implementation**

内存构造 `ExecutionResult` 时 `generated_code=""`。已知迭代次数用同等数量的 `IterationResult` 占位，只提供构造函数必填字段的空值。缺失 `iterations` 的行不进入会把空轨迹当成 1 的导出器。

CSV 列名复制 `CSVExporter.export` 的 `fieldnames`。测试计数字段和缺失的 `iterations` 写空字符串。文件使用 `utf-8-sig`。

Markdown 与 HTML 把生成器返回的字符串作为响应体。生成器需要路径时写入 `tempfile.TemporaryDirectory`，读回返回值后删除目录。HTML 保持 `include_charts=True`。路由设置 `Content-Disposition: attachment`。

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/test_api_evaluation_results.py::test_reports_match_json_and_blank_missing_csv_fields -q --no-cov`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add api/services/evaluation_results_service.py api/routes/evaluation_results.py tests/test_api_evaluation_results.py
git commit -m "feat: export evaluation reports from stored summaries"
```

### Task 9: 覆盖率与 API 文档

- [ ] Task 9: 覆盖率与 API 文档

对应 `tasks.md` 4.1 和 4.2。

**Files:**
- Modify: `API.md`
- Test: `tests/test_api_evaluation_results.py`、`tests/test_evaluation_result_iterations.py`

- [ ] **Step 1: Write the failing coverage check**

Run:

```bash
python3 -m pytest tests/test_api_evaluation_results.py tests/test_evaluation_result_iterations.py -q --cov=api/routes/evaluation_results.py --cov=api/services/evaluation_results_service.py --cov=src/tasks/evaluation.py --cov-fail-under=80
```

Expected: 若新增分支未覆盖则 FAIL。缺的断言只补本计划已列口径：空学习曲线、未知成本、缺失迭代、他人 CSV、详情分页。

- [ ] **Step 2: Document the endpoints**

在 `API.md` 增加一节，列出本计划全部路径、`ApiResponse` 外壳、分页、404 和报告的 Content-Type。写明统计与 CLI 的成功率、解出数、token、成本使用同一落库聚合；报告不含生成代码和沙箱轨迹。

- [ ] **Step 3: Run the focused tests and coverage**

Run the command in Step 1 again.

Expected: PASS，覆盖率大于 80%。

- [ ] **Step 4: Commit**

```bash
git add API.md tests/test_api_evaluation_results.py tests/test_evaluation_result_iterations.py
git commit -m "docs: describe the evaluation results API"
```
