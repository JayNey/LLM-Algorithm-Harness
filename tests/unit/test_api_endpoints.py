"""HTTP boundary unit tests for issue #158 section 3.

Use the real application/router/middleware but never enter its lifespan. Services,
DB sessions and queue dispatch are replaced, so no provider, Docker or Redis is
needed. Existing tests/test_api_* suites cover the underlying business behavior.
"""

import asyncio
import time
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import BoundedSemaphore
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, Mock, call

import pytest
from fastapi.routing import APIRoute, APIWebSocketRoute
from fastapi.testclient import TestClient

from api.auth.service import AuthService, Principal
from api.db.engine import get_db
from api.files.config import FileSettings
from api.files.service import FileService
from api.files.templates import TEMPLATES, template
from api.main import create_app
from api.monitoring.service import MonitorService
from api.progress import Subscription
from api.routes.tasks import task_manager
from api.schemas import EvaluationResponse, ExecutionProgress, ProgressInfo
from api.services import (
    ABTestService,
    BenchmarkService,
    CostService,
    EvaluationResultsService,
    EvaluationService,
    ExperimentService,
)
from api.services.evaluation_options_service import EvaluationOptionsService
from src.task_manager import TaskManager

pytestmark = pytest.mark.unit
OWNER = "unit-owner"
PRINCIPAL = Principal(user_id=OWNER, session_id="unit-session")
PREFIX = "/api/v1"
VALUE = {"id": "resource-1", "value": "service-result"}
EVALUATION = EvaluationResponse(
    evaluation_id="eval-1",
    created_at="2026-10-19T00:00:00Z",
    updated_at="2026-10-19T00:00:00Z",
    status="pending",
    can_start=True,
    can_cancel=False,
    execution_progress=ExecutionProgress(completed_units=0, total_units=1, percentage=0.0),
    strategy_names=["vanilla"],
    problem_count=1,
    spent_usd=0,
)
EVAL_BODY = dict(
    api_key_id="key-1", model="test-model", problem_ids=["p1"], strategy_names=["vanilla"]
)
EVAL_OPTIONS = dict(
    strategies=[dict(name="vanilla")],
    sources=[dict(id="shared", label="共享题库", problem_count=1)],
)
PROBLEM_OPTIONS = dict(
    items=[dict(problem_id="p1", title="示例题目", difficulty="easy", source="shared")],
    total=1,
    limit=20,
    offset=0,
    has_more=False,
)
MODEL_OPTIONS = dict(provider="openai", models=["test-model"], complete=True)
EXPERIMENT_BODY = dict(
    dataset_path="dataset.json",
    models=[{"model": "test-model"}],
    strategies=[{"name": "vanilla"}],
    api_key_id="key-1",
)
SUITE_BODY = dict(name="unit-suite", problems=["p1"])
RUN_BODY = dict(dataset_path="dataset.json", model="test-model", api_key_id="key-1")
AB_BODY = dict(
    dataset_path="dataset.json",
    model={"model": "test-model"},
    strategy={"name": "vanilla"},
    prompt_variants=[{"id": "a", "prefix": "A"}, {"id": "b", "prefix": "B"}],
    api_key_id="key-1",
)
TASK_BODY = dict(
    task_type="evaluation",
    entity_id="eval-1",
    celery_task_name="src.tasks.evaluation.run_evaluation_task",
)


@dataclass
class Case:
    method: str
    path: str
    target: str | None = None
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)
    body: dict | None = None
    result: object = field(default_factory=lambda: VALUE.copy())
    status: int = 200
    expected: object = field(default_factory=lambda: VALUE.copy())
    public: bool = False
    admin: bool = False
    multipart: bool = False
    download: bool = False

    @property
    def id(self):
        return f"{self.method} {self.path}"


def case(method, path, target=None, args=(), **kwargs):
    return Case(method, path, target, args, **kwargs)


CASES = [
    case(
        "GET",
        "/health",
        expected={
            "status": "healthy",
            "scope": "api_liveness_only",
            "version": "0.1.0",
            "service": "LLM Algorithm Harness API",
        },
        public=True,
    ),
    case(
        "POST",
        "/auth/register",
        "auth.register",
        (ANY,),
        body=dict(username="unit-user", email="unit@example.org", password="unit-password-123"),
        status=201,
        public=True,
    ),
    case(
        "POST",
        "/auth/login",
        "auth.login",
        ("unit-user", "unit-password-123"),
        body=dict(username="unit-user", password="unit-password-123"),
        public=True,
    ),
    case(
        "POST",
        "/auth/refresh",
        "auth.refresh",
        ("refresh-token",),
        body=dict(refresh_token="refresh-token"),
        public=True,
    ),
    case("POST", "/auth/logout", "auth.logout", (PRINCIPAL,), status=204),
    case("GET", "/users/me", "auth.public_user", (OWNER,), expected={**VALUE, "role": "admin"}),
    case(
        "POST",
        "/users/me/password",
        "auth.change_password",
        (PRINCIPAL, ANY),
        body=dict(current_password="old-password", new_password="unit-password-123"),
        status=204,
    ),
    case(
        "PATCH", "/users/me", "auth.update_user", (PRINCIPAL, ANY), body=dict(username="unit-user")
    ),
    case("GET", "/api-keys", "auth.store.keys", (OWNER,), result=[], expected=[]),
    case(
        "POST",
        "/api-keys",
        "auth.add_key",
        (OWNER, ANY),
        body=dict(provider="openai", key_name="unit-key", api_key="fake-provider-key"),
        status=201,
    ),
    case(
        "PATCH",
        "/api-keys/{key_id}",
        "auth.update_key",
        ("key-1", OWNER, ANY),
        body=dict(key_name="renamed"),
    ),
    case("DELETE", "/api-keys/{key_id}", "auth.delete_key", ("key-1", OWNER), status=204),
    case("POST", "/api-keys/{key_id}/verify", "auth.verify_key", ("key-1", OWNER)),
    case(
        "GET",
        "/evaluation-options",
        "evaluation_options.options",
        (OWNER,),
        result=EVAL_OPTIONS,
        expected=EVAL_OPTIONS,
    ),
    case(
        "GET",
        "/evaluation-options/problems",
        "evaluation_options.problems",
        (OWNER, "all", 20, 0),
        result=PROBLEM_OPTIONS,
        expected=PROBLEM_OPTIONS,
    ),
    case(
        "GET",
        "/evaluation-options/models",
        "evaluation_options.models",
        (OWNER, "key-1"),
        result=MODEL_OPTIONS,
        expected=MODEL_OPTIONS,
    ),
    case(
        "POST",
        "/evaluations",
        "evaluations.create_evaluation",
        (ANY, OWNER),
        body=EVAL_BODY,
        result=EVALUATION,
        expected=EVALUATION.model_dump(),
        status=201,
    ),
    case(
        "GET",
        "/evaluations",
        "evaluations.list_evaluations",
        (OWNER,),
        kwargs=dict(status=None, limit=20, offset=0),
        result=([EVALUATION], 1),
        expected=None,
    ),
    case(
        "GET",
        "/evaluations/{evaluation_id}",
        "evaluations.get_evaluation",
        ("eval-1", OWNER),
        result=EVALUATION,
        expected=EVALUATION.model_dump(),
    ),
    case(
        "PATCH",
        "/evaluations/{evaluation_id}",
        "evaluations.update_evaluation",
        ("eval-1", ANY, OWNER),
        body=dict(budget_cap_usd=0),
        result=EVALUATION,
        expected=EVALUATION.model_dump(),
    ),
    case(
        "DELETE",
        "/evaluations/{evaluation_id}",
        "evaluations.delete_evaluation",
        ("eval-1", OWNER, ANY),
        status=204,
    ),
    case(
        "POST",
        "/evaluations/{evaluation_id}/start",
        "evaluations.start_evaluation",
        ("eval-1", OWNER),
        result=EVALUATION,
        expected=EVALUATION.model_dump(),
        status=202,
    ),
    case(
        "GET",
        "/evaluations/{evaluation_id}/progress",
        "evaluations.get_progress",
        ("eval-1", OWNER),
        result=ProgressInfo(current=0, total=1),
        expected=ProgressInfo(current=0, total=1).model_dump(),
    ),
    case(
        "POST",
        "/evaluations/{evaluation_id}/cancel",
        "evaluations.cancel_evaluation",
        ("eval-1", OWNER),
        result=EVALUATION,
        expected=EVALUATION.model_dump(),
    ),
    case(
        "POST",
        "/experiments",
        "experiments.create_experiment",
        (ANY, OWNER),
        body=EXPERIMENT_BODY,
        status=201,
    ),
    case(
        "GET",
        "/experiments",
        "experiments.list_experiments",
        (OWNER,),
        kwargs=dict(status=None, limit=20, offset=0),
        result=([VALUE], 1),
        expected=None,
    ),
    case("GET", "/experiments/{experiment_id}", "experiments.get_experiment", ("exp-1", OWNER)),
    case(
        "DELETE",
        "/experiments/{experiment_id}",
        "experiments.delete_experiment",
        ("exp-1", OWNER),
        status=204,
    ),
    case(
        "POST",
        "/experiments/{experiment_id}/run",
        "experiments.start_experiment",
        ("exp-1", OWNER),
        status=202,
    ),
    case(
        "GET",
        "/benchmarks/suites",
        "benchmarks.list_suites",
        (OWNER,),
        result=[VALUE],
        expected=None,
    ),
    case(
        "POST",
        "/benchmarks/suites",
        "benchmarks.create_suite",
        (ANY, OWNER),
        body=SUITE_BODY,
        status=201,
    ),
    case("GET", "/benchmarks/suites/{suite_id}", "benchmarks.get_suite", ("suite-1", OWNER)),
    case(
        "PATCH",
        "/benchmarks/suites/{suite_id}",
        "benchmarks.update_suite",
        ("suite-1", ANY, OWNER),
        body=dict(frozen=True),
    ),
    case(
        "POST",
        "/benchmarks/suites/{suite_id}/run",
        "benchmarks.start_run",
        ("suite-1", ANY, OWNER),
        body=RUN_BODY,
        status=202,
    ),
    case("GET", "/benchmarks/runs/{run_id}", "benchmarks.get_run", ("run-1", OWNER)),
    case(
        "GET",
        "/benchmarks/learning-curve/{suite_id}",
        "benchmarks.learning_curve",
        ("suite-1", OWNER),
    ),
    case("POST", "/ab-tests", "ab_tests.create_test", (ANY, OWNER), body=AB_BODY, status=201),
    case(
        "GET",
        "/ab-tests",
        "ab_tests.list_tests",
        (OWNER,),
        kwargs=dict(status=None, limit=20, offset=0),
        result=([VALUE], 1),
        expected=None,
    ),
    case("GET", "/ab-tests/{test_id}", "ab_tests.get_test", ("ab-1", OWNER)),
    case("DELETE", "/ab-tests/{test_id}", "ab_tests.delete_test", ("ab-1", OWNER), status=204),
    case("POST", "/ab-tests/{test_id}/run", "ab_tests.start_test", ("ab-1", OWNER), status=202),
    case("GET", "/ab-tests/{test_id}/results", "ab_tests.results", ("ab-1", OWNER)),
    case(
        "GET",
        "/results",
        "evaluation_results.list_runs",
        (OWNER,),
        kwargs=dict(
            strategy=None,
            difficulty=None,
            tag=None,
            status=None,
            limit=20,
            offset=0,
            sort="completed_at",
            order="desc",
        ),
        result=([VALUE], 1),
        expected=None,
    ),
    case(
        "GET",
        "/results/problems/{problem_id}",
        "evaluation_results.problem_history",
        (OWNER, "p1"),
        kwargs=dict(status=None, limit=20, offset=0),
        result=([VALUE], 1),
        expected=None,
    ),
    case(
        "GET",
        "/results/{run_id}",
        "evaluation_results.detail",
        (OWNER, "run-1"),
        kwargs=dict(limit=20, offset=0),
    ),
    case("GET", "/compare/models", "evaluation_results.compare_models", (OWNER,)),
    case("GET", "/compare/ab-test/{test_id}", "ab_tests.results", ("ab-1", OWNER)),
    case(
        "GET",
        "/visualizations/learning-curve",
        "evaluation_results.learning_curve",
        (OWNER,),
        kwargs=dict(suite_id=None),
    ),
    case("GET", "/costs/tasks/{task_id}", "cost.task_cost", ("task-1", OWNER)),
    case("GET", "/budgets", "cost.get_budget", (OWNER,)),
    case(
        "POST",
        "/budgets",
        "cost.upsert_budget",
        (ANY, OWNER),
        body=dict(global_cap_usd=1),
        status=201,
    ),
    case(
        "PATCH",
        "/budgets",
        "cost.upsert_budget",
        (ANY, OWNER),
        kwargs=dict(partial=True),
        body=dict(action="pause"),
    ),
    case("GET", "/budgets/usage", "cost.budget_usage", (OWNER,)),
    case("GET", "/alerts", "cost.list_rules", (OWNER,), result=[VALUE], expected=[VALUE]),
    case(
        "POST",
        "/alerts",
        "cost.create_rule",
        (ANY, OWNER),
        body=dict(threshold_pct=1, channel="log"),
        status=201,
    ),
    case(
        "PATCH",
        "/alerts/{rule_id}",
        "cost.update_rule",
        ("rule-1", ANY, OWNER),
        body=dict(enabled=False),
    ),
    case("DELETE", "/alerts/{rule_id}", "cost.delete_rule", ("rule-1", OWNER), status=204),
    case(
        "GET",
        "/alerts/history",
        "cost.alert_history",
        (OWNER,),
        kwargs=dict(limit=50),
        result=[VALUE],
        expected=[VALUE],
    ),
    case("GET", "/pricing", "cost.pricing_catalog"),
    case(
        "GET",
        "/pricing/{model_id}/history",
        "cost.pricing_history",
        ("test-model",),
        result=[VALUE],
        expected=[VALUE],
    ),
    case(
        "POST",
        "/pricing/{model_id}",
        "cost.set_pricing_override",
        ("test-model", ANY, OWNER),
        body=dict(prompt_per_1k=0.01, completion_per_1k=0.02),
        status=201,
    ),
    case("GET", "/reports/cost/{task_id}", "cost.task_report", ("task-1", OWNER)),
    case("GET", "/reports/cost-optimization", "cost.cost_optimization_report", (OWNER,)),
]
for suffix, operation in [("results", "results"), ("comparison", "comparison"), ("panel", "panel")]:
    CASES.append(
        case(
            "GET",
            f"/experiments/{{experiment_id}}/{suffix}",
            f"experiments.{operation}",
            ("exp-1", OWNER),
        )
    )
for suffix in ["summary", "trends", "breakdown"]:
    CASES.append(case("GET", f"/costs/{suffix}", f"cost.{suffix}", (OWNER, None, None)))
for path, operation in [
    ("analytics/success-rate", "success_rate"),
    ("analytics/tokens", "tokens"),
    ("analytics/iterations", "iterations"),
    ("analytics/failure-modes", "failure_modes"),
    ("visualizations/success-rate-chart", "success_rate_chart"),
    ("visualizations/token-chart", "token_chart"),
    ("visualizations/cost-accuracy", "cost_accuracy"),
    ("visualizations/capability-radar", "capability_radar"),
    ("failures/by-tag", "failures_by_tag"),
]:
    CASES.append(
        case(
            "GET",
            f"/{path}",
            f"evaluation_results.{operation}",
            (OWNER,),
            kwargs=dict(run_id=None, strategy=None, difficulty=None, tag=None),
        )
    )
for suffix in ["summary", "cases"]:
    CASES.append(
        case(
            "GET",
            f"/failures/{suffix}/{{run_id}}",
            f"evaluation_results.failure_{suffix}",
            (OWNER, "run-1"),
        )
    )
for suffix in ["strategies", "history"]:
    CASES.append(
        case("GET", f"/compare/{suffix}", f"evaluation_results.compare_{suffix}", (OWNER, "run-1"))
    )
for fmt in ["markdown", "html", "csv"]:
    CASES.append(
        case(
            "GET",
            f"/reports/{fmt}/{{run_id}}",
            f"evaluation_results.report_{fmt}",
            (OWNER, "run-1"),
            result="report-content",
            expected=b"report-content",
            download=True,
        )
    )
for path, target, args in [
    ("system/health", "health", (False,)),
    ("health/database", "probes.database", ()),
    ("health/redis", "probes.redis", ()),
    ("health/workers", "probes.workers", ()),
    ("system/workers", "probes.workers", ()),
    ("health/sandbox", "probes.sandbox", ()),
    ("system/resources", "probes.resources", ()),
    ("metrics/api-stats", "store.api_stats", (60,)),
    ("metrics/performance", "performance", ()),
    ("metrics/llm-stats", "llm_stats", ()),
    ("metrics/cache-stats", "probes.cache_stats", (ANY,)),
    ("config/providers", "probes.providers", ()),
    ("config/sandbox", "probes.sandbox_config", ()),
]:
    CASES.append(case("GET", f"/{path}", f"monitor.{target}", args, admin=True))
for path, state in [("running", "running"), ("queued", "pending")]:
    CASES.append(
        case(
            "GET",
            f"/system/tasks/{path}",
            "monitor.task_snapshot",
            (state, 100, 0, "legacy_evaluation"),
            admin=True,
        )
    )
for path in ["quotas", "quotas/usage"]:
    CASES.append(case("GET", f"/{path}", "monitor.quotas", (OWNER,)))
CASES += [
    case(
        "GET",
        "/config/strategies",
        "monitor.probes.strategies",
        result=[],
        expected={"strategies": []},
        admin=True,
    ),
    case(
        "GET",
        "/system/status",
        "monitor.task_snapshot",
        result=dict(counts={}, total=0, status="available", source="unit"),
        expected=None,
        admin=True,
    ),
    case(
        "GET",
        "/logs",
        "monitor.store.query_logs",
        kwargs=dict(level=None, start=None, end=None, search=None, limit=100, offset=0),
        result=([VALUE], 1),
        expected=None,
        admin=True,
    ),
    case(
        "GET",
        "/logs/tasks/{task_id}",
        "monitor.store.query_logs",
        kwargs=dict(
            level=None,
            start=None,
            end=None,
            search=None,
            limit=100,
            offset=0,
            user_id=OWNER,
            run_id="task-1",
        ),
        result=([VALUE], 1),
        expected=None,
    ),
    case(
        "GET",
        "/logs/download/{task_id}",
        "monitor.store.export_logs",
        (ANY,),
        kwargs=dict(level=None, start=None, end=None, search=None, user_id=OWNER, run_id="task-1"),
        result=dict(total=0, exported=0, truncated=False),
        expected=b"",
        download=True,
    ),
    case(
        "POST",
        "/files/upload",
        "files.upload",
        (ANY, "fixture.json", "application/json", OWNER),
        result={"file": {"id": "file-1"}},
        expected={"file": {"id": "file-1"}},
        status=201,
        multipart=True,
    ),
    case(
        "POST",
        "/configs/upload",
        "files.upload",
        (ANY, "fixture.json", "application/json", OWNER, "harness"),
        result={"file": {"id": "file-1"}},
        expected={"file": {"id": "file-1"}},
        status=201,
        multipart=True,
    ),
    case(
        "POST",
        "/problems/upload",
        "files.upload",
        (ANY, "fixture.json", "application/json", OWNER),
        result={"file": {"id": "file-1"}},
        expected={"file_id": "file-1", "job_id": "job-1", "validation": {}},
        multipart=True,
    ),
    case(
        "POST",
        "/problems/import",
        "manager.enqueue_task",
        (),
        kwargs=dict(
            task_type="import",
            entity_id="job-1",
            user_id=OWNER,
            celery_task_name="src.tasks.imports.run_import_task",
            celery_task_args=("job-1", OWNER),
        ),
        body=dict(file_id="file-1"),
        result=SimpleNamespace(id="task-1"),
        expected={"job_id": "job-1", "task_id": "task-1", "status": "pending"},
        status=202,
    ),
    case(
        "GET",
        "/imports/{job_id}",
        "files.store.job",
        ("job-1", OWNER),
        result=dict(status="completed", total=0, processed=0, result={}),
        expected=dict(
            job_id="job-1", status="completed", total=0, processed=0, percentage=100, result={}
        ),
    ),
    case(
        "GET",
        "/configs/templates",
        expected=[{"name": name, "type": value["type"]} for name, value in TEMPLATES.items()],
    ),
    case("GET", "/configs/templates/{name}", expected=template(next(iter(TEMPLATES)))),
    case("GET", "/files/{file_id}", "files.store.owned_file", ("file-1", OWNER), expected=VALUE),
    case(
        "GET",
        "/files/{file_id}/download",
        "files.read_file",
        ("file-1", OWNER),
        result=({"suffix": ".json", "filename": "fixture.json"}, b"{}"),
        expected=b"{}",
        download=True,
    ),
    case("DELETE", "/files/{file_id}", "files.delete_file", ("file-1", OWNER), status=204),
    case(
        "GET",
        "/problems/export",
        "files.export_dataset",
        (OWNER, "json"),
        result=("fixture.json", "application/json", b"[]"),
        expected=b"[]",
        download=True,
    ),
]
for suffix in ["download", "export"]:
    CASES.append(
        case(
            "GET",
            f"/results/{{run_id}}/{suffix}",
            "files.export_results",
            ("run-1", OWNER, "json"),
            result=("fixture.json", "application/json", b"{}"),
            expected=b"{}",
            download=True,
        )
    )
CASES.append(
    case(
        "GET",
        "/results/{run_id}/charts/{chart_name}",
        "files.export_results",
        ("run-1", OWNER, "png"),
        result=("chart.png", "image/png", b"png-bytes"),
        expected=b"png-bytes",
        download=True,
    )
)

TASK = SimpleNamespace(
    id="task-1",
    task_type="evaluation",
    entity_id="eval-1",
    celery_task_id="celery-1",
    status="pending",
    progress=None,
    error_message=None,
    created_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
    updated_at=datetime(2026, 10, 19, tzinfo=timezone.utc),
    started_at=None,
    completed_at=None,
)
TASK_DATA = {
    key: value.isoformat() if isinstance(value, datetime) else value
    for key, value in vars(TASK).items()
}
CASES += [
    case(
        "POST",
        "/tasks",
        "manager.enqueue_task",
        kwargs=dict(
            task_type="evaluation",
            entity_id="eval-1",
            user_id=OWNER,
            celery_task_name=TASK_BODY["celery_task_name"],
            celery_task_args=(),
            celery_task_kwargs={},
        ),
        body=TASK_BODY,
        result=TASK,
        expected=TASK_DATA,
        status=201,
    ),
    case(
        "GET",
        "/tasks",
        "manager.list_tasks",
        kwargs=dict(user_id=OWNER, task_type=None, status=None, limit=20, offset=0),
        result=([TASK], 1),
        expected=None,
    ),
    case(
        "GET",
        "/tasks/{task_id}",
        "manager.get_task",
        ("task-1", OWNER),
        result=TASK,
        expected=TASK_DATA,
    ),
    case(
        "DELETE",
        "/tasks/{task_id}",
        "manager.cancel_task",
        ("task-1", OWNER),
        result=TASK,
        expected=TASK_DATA,
    ),
    case(
        "POST",
        "/tasks/{task_id}/pause",
        "manager.pause_task",
        ("task-1", OWNER),
        result=TASK,
        expected=TASK_DATA,
    ),
    case(
        "POST",
        "/tasks/{task_id}/resume",
        "manager.resume_task",
        ("task-1", OWNER),
        result=TASK,
        expected=TASK_DATA,
    ),
    case(
        "POST",
        "/pareto/analyze",
        "pareto_analysis",
        ([{}],),
        kwargs=dict(budgets=[], accuracy_metric="overall"),
        body=dict(comparisons=[{}]),
    ),
    case(
        "POST",
        "/optimize",
        "advisory",
        ({},),
        kwargs=dict(budget=None, min_accuracy=0.0, objective="best_value"),
        body=dict(comparison={}),
    ),
]


def url(item):
    return (
        PREFIX
        + item.path.format(
            key_id="key-1",
            evaluation_id="eval-1",
            experiment_id="exp-1",
            suite_id="suite-1",
            run_id="run-1",
            test_id="ab-1",
            problem_id="p1",
            task_id="task-1",
            rule_id="rule-1",
            model_id="test-model",
            file_id="file-1",
            job_id="job-1",
            name=next(iter(TEMPLATES)),
            chart_name="success-rate",
        )
        + ("?run_id=run-1" if item.path in {"/compare/strategies", "/compare/history"} else "")
        + ("?api_key_id=key-1" if item.path == "/evaluation-options/models" else "")
    )


def target(api, name):
    obj = api
    for part in name.split("."):
        obj = getattr(obj, part)
    return obj


@pytest.fixture(scope="module")
def unit_app():
    return create_app()


@pytest.fixture
def api(monkeypatch, tmp_path, unit_app):
    app = unit_app
    services = {
        name: Mock(spec=cls)
        for name, cls in dict(
            auth=AuthService,
            files=FileService,
            evaluations=EvaluationService,
            evaluation_options=EvaluationOptionsService,
            evaluation_results=EvaluationResultsService,
            experiments=ExperimentService,
            benchmarks=BenchmarkService,
            ab_tests=ABTestService,
            cost=CostService,
            monitor=MonitorService,
            manager=TaskManager,
        ).items()
    }
    state = SimpleNamespace(app=app, **services)
    # Instance attributes are intentionally concrete rather than auto-created Mocks.
    state.auth.settings = SimpleNamespace(AUTH_PROTECTED_RATE_LIMIT=10000)
    state.auth.authenticate.return_value = PRINCIPAL
    state.auth.store = Mock()
    state.auth.store.keys.return_value = []
    state.files.auth = state.auth
    state.files.settings = FileSettings(_env_file=None, UPLOAD_DIR=tmp_path)
    state.files.transfers = BoundedSemaphore(1)
    state.files.store = Mock()
    state.files.store.create_job.return_value = "job-1"
    state.files.store.job.return_value = dict(status="completed", total=0, processed=0, result={})
    state.files.metadata.return_value = VALUE.copy()
    state.monitor.settings = SimpleNamespace(is_admin=lambda user_id: user_id == OWNER)
    state.monitor.probes = Mock()
    state.monitor.store = Mock()
    state.monitor.files = state.files
    state.monitor.cache = Mock()
    state.monitor.started = time.monotonic()
    state.files.store.connection.return_value = nullcontext(Mock())
    state.evaluations.credential_id.return_value = "key-1"
    worker_observation = {
        "status": "ok",
        "worker_count": 1,
        "active": 0,
        "reserved": 0,
        "concurrency": 1,
    }
    state.monitor.health.return_value = {"checks": {"workers": worker_observation}}
    state.monitor.probes.resources.return_value = {}
    state.monitor.probes.containers.return_value = {
        "status": "not_configured",
        "reason": "disabled",
    }
    state.monitor.probes.workers.return_value = worker_observation
    state.progress_stream = SimpleNamespace(subscribe=AsyncMock(), unsubscribe=AsyncMock())
    for name in services:
        setattr(app.state, name, getattr(state, name))
    app.state.progress_stream = state.progress_stream
    app.dependency_overrides[get_db] = lambda: Mock(name="db-session")
    app.dependency_overrides[task_manager] = lambda: state.manager
    monkeypatch.setattr("api.routes.files.TaskManager", lambda db: state.manager)
    state.pareto_analysis = Mock(return_value=VALUE.copy())
    state.advisory = Mock(return_value=VALUE.copy())
    monkeypatch.setattr("api.routes.ab_tests.build_pareto_analysis", state.pareto_analysis)
    monkeypatch.setattr("api.routes.ab_tests.build_advisory", state.advisory)

    def unexpected_external_call(*args, **kwargs):
        raise AssertionError("Route unit test attempted an external dependency")

    for name in (
        "api.db.engine.make_engine",
        "src.llm_client.LLMClient.__init__",
        "src.sandbox_executor.SandboxExecutor.__init__",
        "socket.create_connection",
    ):
        monkeypatch.setattr(name, unexpected_external_call)
    # Deliberately no `with TestClient(...)`: startup would construct real services.
    state.client = TestClient(app)
    state.client.headers["Authorization"] = "Bearer unit-token"
    yield state
    state.client.close()


def send(api, item, **overrides):
    options = {}
    if item.body is not None:
        options["json"] = item.body
    if item.multipart:
        options["files"] = {"file": ("fixture.json", b"[]", "application/json")}
    options.update(overrides)
    return api.client.request(item.method, url(item), **options)


def assert_submitted_fields(actual, expected):
    if hasattr(actual, "get_secret_value"):
        assert actual.get_secret_value() == expected
    elif isinstance(expected, dict):
        for key, value in expected.items():
            nested = actual[key] if isinstance(actual, dict) else getattr(actual, key)
            assert_submitted_fields(nested, value)
    elif isinstance(expected, list):
        assert len(actual) == len(expected)
        for actual_value, expected_value in zip(actual, expected, strict=True):
            assert_submitted_fields(actual_value, expected_value)
    else:
        assert actual == expected


@pytest.mark.parametrize("item", CASES, ids=lambda item: item.id)
def test_endpoint_happy_path(api, item):
    operation = target(api, item.target) if item.target else None
    if operation is not None:
        operation.return_value = item.result
    response = send(api, item)
    assert response.status_code == item.status, response.text
    assert response.headers["Cache-Control"] == "no-store"
    if operation is not None:
        if item.path == "/system/status":
            assert operation.call_args_list == [call(), call(task_source="async_task")]
        else:
            operation.assert_called_once_with(*item.args, **item.kwargs)
        # Verify supplied fields recursively, including nested models and secrets.
        for arg in operation.call_args.args:
            if hasattr(arg, "model_dump") and item.body:
                assert_submitted_fields(arg, item.body)
    if item.status == 204:
        assert response.content == b""
    elif item.download:
        assert response.content == item.expected
        assert "attachment" in response.headers["Content-Disposition"]
    else:
        body = response.json()
        assert body["success"] is True
        assert body["message"]
        if item.expected is not None:
            assert body["data"] == item.expected
        elif isinstance(item.result, tuple):
            assert body["data"]["total"] == 1
            assert len(body["data"]["items"]) == 1
        elif item.path == "/system/status":
            assert body["data"]["async_task_count"] == 0
            assert body["data"]["workers"] == body["data"]["health"]["checks"]["workers"]
            api.monitor.health.assert_called_once_with()
            api.monitor.probes.workers.assert_not_called()
        elif item.path == "/benchmarks/suites":
            assert body["data"]["items"] == [VALUE]
        else:
            assert body["data"] == VALUE
    if item.path.startswith("/logs/"):
        api.files.store.check_run.assert_called_once_with(ANY, "task-1", OWNER)
    if item.path == "/evaluations" and item.method == "POST":
        api.auth.owned_key.assert_called_once_with("key-1", OWNER)
        api.files.store.register_run.assert_called_once_with("eval-1", OWNER)
    if item.path == "/evaluations/{evaluation_id}/start":
        api.auth.owned_key.assert_called_once_with("key-1", OWNER)


def registered_routes(router):
    # FastAPI supports both flattened and lazily included routers.
    for route in router.routes:
        nested = getattr(route, "original_router", None)
        if nested is not None:
            yield from registered_routes(nested)
        else:
            yield route


def test_every_registered_endpoint_has_an_explicit_happy_path_case(api):
    routes = list(registered_routes(api.app))
    actual = {
        (method, route.path)
        for route in routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }
    declared = [(item.method, PREFIX + item.path) for item in CASES]
    assert len(declared) == len(set(declared)), "Duplicate test cases hide omissions"
    assert set(declared) == actual
    assert [route.path for route in routes if isinstance(route, APIWebSocketRoute)] == [
        PREFIX + "/ws/progress"
    ]


@pytest.mark.parametrize(
    "item", [item for item in CASES if not item.public], ids=lambda item: item.id
)
def test_every_protected_endpoint_requires_authentication(api, item):
    api.client.headers.pop("Authorization")
    response = send(api, item)
    assert response.status_code == 401, response.text
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert response.headers["WWW-Authenticate"] == "Bearer"
    if item.target:
        target(api, item.target).assert_not_called()


@pytest.mark.parametrize("item", [item for item in CASES if item.admin], ids=lambda item: item.id)
def test_monitoring_rejects_non_admin_before_probing(api, item):
    api.monitor.settings.is_admin = lambda user_id: False
    response = send(api, item)
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "FORBIDDEN"
    target(api, item.target).assert_not_called()


def test_websocket_snapshot_ping_and_cleanup(api):
    subscription = Subscription(channel="progress:eval-1", queue=asyncio.Queue())
    api.progress_stream.subscribe.return_value = subscription
    api.evaluations.get_evaluation.return_value = EVALUATION
    with api.client.websocket_connect(PREFIX + "/ws/progress?token=unit-token") as ws:
        assert ws.receive_json() == {"type": "connected", "user_id": OWNER}
        ws.send_json({"action": "subscribe", "task_id": "eval-1"})
        assert ws.receive_json() == {
            "type": "task.snapshot",
            "task_id": "eval-1",
            "data": EVALUATION.model_dump(),
        }
        assert ws.receive_json() == {"type": "subscribed", "task_id": "eval-1"}
        ws.send_json({"action": "ping"})
        assert ws.receive_json() == {"type": "pong"}
    api.progress_stream.subscribe.assert_awaited_once_with("progress:eval-1")
    api.evaluations.get_evaluation.assert_called_once_with("eval-1", OWNER)
    api.progress_stream.unsubscribe.assert_awaited_once_with(subscription)


def assert_error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == code
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]
    assert response.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "item", [item for item in CASES if not item.public], ids=lambda item: item.id
)
def test_invalid_token_never_reaches_protected_operation(api, item):
    from api.auth.service import unauthorized
    from api.middleware.errors import ErrorCode

    api.auth.authenticate.side_effect = unauthorized(ErrorCode.INVALID_TOKEN)
    response = send(api, item)
    assert_error(response, 401, "INVALID_TOKEN")
    if item.target:
        target(api, item.target).assert_not_called()


@pytest.mark.parametrize("item", [item for item in CASES if item.target], ids=lambda item: item.id)
def test_service_http_errors_preserve_status_and_request_id(api, item):
    from fastapi import HTTPException

    operation = target(api, item.target)
    operation.side_effect = HTTPException(404, "Resource not found")
    response = send(api, item)
    assert_error(response, 404, "RESOURCE_NOT_FOUND")
    assert operation.call_count == 1


@pytest.mark.parametrize("item", [item for item in CASES if item.target], ids=lambda item: item.id)
def test_unexpected_dependency_failures_are_sanitized(api, item, caplog):
    operation = target(api, item.target)
    operation.side_effect = RuntimeError("private-provider-token-unit-test")
    response = send(api, item)
    assert_error(response, 500, "INTERNAL_ERROR")
    assert "private-provider-token-unit-test" not in response.text + caplog.text
    assert operation.call_count == 1


# These operations explicitly translate domain ValueErrors to 400/404 at the route
# boundary. Other services raise HTTPException themselves (covered above).
VALUE_ERROR_PATHS = {
    "/evaluations/{evaluation_id}",
    "/evaluations/{evaluation_id}/start",
    "/evaluations/{evaluation_id}/progress",
    "/evaluations/{evaluation_id}/cancel",
    "/experiments",
    "/experiments/{experiment_id}",
    "/experiments/{experiment_id}/run",
    "/experiments/{experiment_id}/results",
    "/experiments/{experiment_id}/comparison",
    "/experiments/{experiment_id}/panel",
    "/benchmarks/suites/{suite_id}",
    "/benchmarks/suites/{suite_id}/run",
    "/benchmarks/runs/{run_id}",
    "/benchmarks/learning-curve/{suite_id}",
    "/ab-tests/{test_id}",
    "/ab-tests/{test_id}/run",
    "/ab-tests/{test_id}/results",
    "/tasks/{task_id}",
    "/tasks/{task_id}/pause",
    "/tasks/{task_id}/resume",
    "/results/{run_id}",
    "/compare/strategies",
    "/compare/history",
    "/compare/ab-test/{test_id}",
    "/costs/tasks/{task_id}",
    "/costs/summary",
    "/costs/trends",
    "/costs/breakdown",
    "/reports/cost/{task_id}",
    "/alerts/{rule_id}",
}
VALUE_ERROR_CASES = [
    item
    for item in CASES
    if item.path in VALUE_ERROR_PATHS
    and item.target
    and not item.target.endswith(("list_experiments",))
]


@pytest.mark.parametrize("item", VALUE_ERROR_CASES, ids=lambda item: item.id)
@pytest.mark.parametrize(
    ("message", "status", "code"),
    [
        ("Resource not found or access denied", 404, "RESOURCE_NOT_FOUND"),
        ("Operation not allowed in current state", 400, "INVALID_PARAMETER"),
    ],
)
def test_domain_errors_map_to_client_responses(api, item, message, status, code):
    target(api, item.target).side_effect = ValueError(message)
    assert_error(send(api, item), status, code)


INVALID_BODIES = [
    ("POST", "/auth/register", {"username": "x"}),
    ("POST", "/auth/login", {"username": ""}),
    ("POST", "/auth/refresh", {"refresh_token": ""}),
    ("PATCH", "/users/me", {"username": "x"}),
    ("POST", "/users/me/password", {"current_password": "old", "new_password": "short"}),
    ("POST", "/api-keys", {"provider": "unknown", "key_name": "key", "api_key": "fake"}),
    ("PATCH", "/api-keys/{key_id}", {"api_key": "env:OPENAI_API_KEY"}),
    ("POST", "/evaluations", {**EVAL_BODY, "problem_ids": []}),
    ("POST", "/evaluations", {**EVAL_BODY, "strategy_names": ["vanilla", "vanilla"]}),
    ("POST", "/evaluations", {**EVAL_BODY, "problem_ids": ["p1", "p1"]}),
    ("POST", "/evaluations", {**EVAL_BODY, "timeout_seconds": 0}),
    ("POST", "/evaluations", {**EVAL_BODY, "max_concurrency": 0}),
    ("POST", "/evaluations", {**EVAL_BODY, "budget_cap_usd": -1}),
    ("PATCH", "/evaluations/{evaluation_id}", {"timeout_seconds": 0}),
    ("POST", "/experiments", {**EXPERIMENT_BODY, "models": []}),
    ("POST", "/experiments", {**EXPERIMENT_BODY, "max_workers": 17}),
    ("POST", "/benchmarks/suites", {**SUITE_BODY, "problems": []}),
    ("PATCH", "/benchmarks/suites/{suite_id}", {"problems": []}),
    ("POST", "/benchmarks/suites/{suite_id}/run", {**RUN_BODY, "budget_cap_usd": 0}),
    ("POST", "/ab-tests", {**AB_BODY, "prompt_variants": [{"id": "a"}]}),
    ("POST", "/ab-tests", {**AB_BODY, "prompt_variants": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}),
    ("POST", "/tasks", {**TASK_BODY, "task_type": ""}),
    ("POST", "/tasks", {**TASK_BODY, "task_type": "x" * 33}),
    ("POST", "/problems/import", {"file_id": "file-1", "mode": "invalid"}),
    ("POST", "/budgets", {"global_cap_usd": 0}),
    ("PATCH", "/budgets", {"difficulty_caps": {"easy": -1}}),
    ("POST", "/alerts", {"threshold_pct": 0, "channel": "log"}),
    ("PATCH", "/alerts/{rule_id}", {"threshold_pct": 101}),
    ("POST", "/pricing/{model_id}", {"prompt_per_1k": 0, "completion_per_1k": 1}),
    ("POST", "/pareto/analyze", {"comparisons": []}),
    ("POST", "/optimize", {"comparison": {}, "min_accuracy": 1.01}),
]


@pytest.mark.parametrize(("method", "path", "body"), INVALID_BODIES)
def test_invalid_body_is_rejected_before_business_operation(api, method, path, body):
    item = next(item for item in CASES if item.method == method and item.path == path)
    assert_error(send(api, item, json=body), 400, "INVALID_PARAMETER")
    if item.target:
        target(api, item.target).assert_not_called()


@pytest.mark.parametrize(
    "path",
    [
        "/evaluations",
        "/experiments",
        "/ab-tests",
        "/tasks",
        "/results",
        "/results/problems/{problem_id}",
    ],
)
@pytest.mark.parametrize(
    ("limit", "offset", "expected_limit", "expected_offset"),
    [
        (0, -1, 20, 0),
        (101, 0, 20, 0),
        (1, 0, 1, 0),
        (100, 2, 100, 2),
    ],
)
def test_pagination_boundaries_and_empty_pages(
    api, path, limit, offset, expected_limit, expected_offset
):
    item = next(item for item in CASES if item.method == "GET" and item.path == path)
    operation = target(api, item.target)
    operation.return_value = ([], 0)
    response = send(api, item, params={"limit": limit, "offset": offset})
    assert response.status_code == 200, response.text
    assert response.json()["data"] == dict(
        items=[], total=0, limit=expected_limit, offset=expected_offset, has_more=False
    )
    assert operation.call_args.kwargs["limit"] == expected_limit
    assert operation.call_args.kwargs["offset"] == expected_offset


@pytest.mark.parametrize(("limit", "expected"), [(0, 1), (1, 1), (200, 200), (201, 200)])
def test_alert_history_limit_is_bounded(api, limit, expected):
    api.cost.alert_history.return_value = []
    assert api.client.get(PREFIX + "/alerts/history", params={"limit": limit}).status_code == 200
    api.cost.alert_history.assert_called_once_with(OWNER, limit=expected)


@pytest.mark.parametrize(
    "query",
    [
        {"limit": 0},
        {"limit": 1001},
        {"offset": -1},
        {"offset": 100001},
        {"level": "unknown"},
        {"search": "x" * 201},
        {"start": "2026-10-19T00:00:00"},
        {"start": "2026-10-20T00:00:00Z", "end": "2026-10-19T00:00:00Z"},
    ],
)
def test_log_filter_boundaries(api, query):
    assert_error(api.client.get(PREFIX + "/logs", params=query), 400, "INVALID_PARAMETER")
    api.monitor.store.query_logs.assert_not_called()


@pytest.mark.parametrize("path", ["/compare/strategies", "/compare/history"])
def test_required_run_id_is_checked_before_service(api, path):
    assert_error(api.client.get(PREFIX + path), 400, "INVALID_PARAMETER")
    api.evaluation_results.compare_strategies.assert_not_called()
    api.evaluation_results.compare_history.assert_not_called()


@pytest.mark.parametrize("path", ["/files/upload", "/configs/upload", "/problems/upload"])
def test_upload_requires_multipart_and_exactly_one_file(api, path):
    assert_error(api.client.post(PREFIX + path, json={}), 415, "UNSUPPORTED_MEDIA_TYPE")
    assert_error(
        api.client.post(PREFIX + path, files={"wrong": ("fixture.json", b"[]")}),
        400,
        "INVALID_PARAMETER",
    )
    api.files.upload.assert_not_called()
    assert api.files.transfers.acquire(blocking=False)
    api.files.transfers.release()


@pytest.mark.parametrize("form", [{"mode": "invalid"}, {"validate": "false"}])
def test_problem_upload_rejects_unsafe_options_before_storage(api, form):
    response = api.client.post(
        PREFIX + "/problems/upload",
        data=form,
        files={"file": ("fixture.json", b"[]", "application/json")},
    )
    assert_error(response, 400, "INVALID_PARAMETER")
    api.files.upload.assert_not_called()


def test_failed_direct_import_removes_uploaded_file(api):
    api.files.upload.return_value = {"file": {"id": "file-1"}}
    api.files.store.job.return_value = dict(
        status="failed", result={"status_code": 400, "detail": "Invalid rows"}
    )
    item = next(item for item in CASES if item.path == "/problems/upload")
    assert_error(send(api, item), 400, "INVALID_PARAMETER")
    api.files.delete_file.assert_called_once_with("file-1", OWNER)


def test_evaluation_registration_failure_rolls_back_created_evaluation(api):
    api.evaluations.create_evaluation.return_value = EVALUATION
    api.files.store.register_run.side_effect = RuntimeError("storage unavailable")
    assert_error(api.client.post(PREFIX + "/evaluations", json=EVAL_BODY), 500, "INTERNAL_ERROR")
    api.evaluations.delete_evaluation.assert_called_once_with("eval-1", OWNER)
    api.auth.audit.assert_not_called()


def test_foreign_provider_key_prevents_evaluation_creation_and_start(api):
    from fastapi import HTTPException

    api.auth.owned_key.side_effect = HTTPException(404, "Key not found")
    assert_error(
        api.client.post(PREFIX + "/evaluations", json=EVAL_BODY), 404, "RESOURCE_NOT_FOUND"
    )
    assert_error(api.client.post(PREFIX + "/evaluations/eval-1/start"), 404, "RESOURCE_NOT_FOUND")
    api.evaluations.create_evaluation.assert_not_called()
    api.evaluations.start_evaluation.assert_not_called()
    api.files.store.register_run.assert_not_called()


def test_unknown_chart_is_rejected_without_export(api):
    assert_error(
        api.client.get(PREFIX + "/results/run-1/charts/unknown"), 404, "RESOURCE_NOT_FOUND"
    )
    api.files.export_results.assert_not_called()


@pytest.mark.parametrize(
    ("status", "total", "processed", "percentage"),
    [
        ("pending", 0, 0, 0),
        ("running", 4, 1, 25),
        ("completed", 0, 0, 100),
    ],
)
def test_import_progress_handles_empty_and_partial_jobs(api, status, total, processed, percentage):
    api.files.store.job.return_value = dict(
        status=status, total=total, processed=processed, result={}
    )
    response = api.client.get(PREFIX + "/imports/job-1")
    assert response.status_code == 200
    assert response.json()["data"]["percentage"] == percentage


def test_websocket_rejects_invalid_token_before_subscription(api):
    from starlette.websockets import WebSocketDisconnect

    api.auth.authenticate.side_effect = ValueError("Invalid token")
    with api.client.websocket_connect(PREFIX + "/ws/progress?token=invalid") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4401
    api.progress_stream.subscribe.assert_not_awaited()


def test_websocket_foreign_task_closes_and_releases_subscription(api):
    from starlette.websockets import WebSocketDisconnect

    subscription = Subscription(channel="progress:foreign", queue=asyncio.Queue())
    api.progress_stream.subscribe.return_value = subscription
    api.evaluations.get_evaluation.side_effect = ValueError("Task not found")
    with api.client.websocket_connect(PREFIX + "/ws/progress?token=unit-token") as ws:
        assert ws.receive_json()["type"] == "connected"
        ws.send_json({"action": "subscribe", "task_id": "foreign"})
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_json()
    assert exc.value.code == 4403
    api.evaluations.get_evaluation.assert_called_once_with("foreign", OWNER)
    api.progress_stream.unsubscribe.assert_awaited_once_with(subscription)


@pytest.mark.parametrize("item", [item for item in CASES if item.public], ids=lambda item: item.id)
def test_public_endpoints_do_not_require_credentials(api, item):
    api.client.headers.pop("Authorization")
    if item.target:
        target(api, item.target).return_value = item.result
    assert send(api, item).status_code == item.status
    api.auth.authenticate.assert_not_called()


@pytest.mark.parametrize("path", ["/pareto/analyze", "/optimize"])
def test_analysis_rejects_invalid_business_payload(api, path):
    item = next(item for item in CASES if item.path == path)
    target(api, item.target).side_effect = ValueError("Invalid comparison")
    assert_error(send(api, item), 400, "INVALID_PARAMETER")


@pytest.mark.parametrize("path", ["/evaluations", "/tasks", "/experiments", "/auth/register"])
def test_malformed_json_does_not_invoke_services(api, path):
    item = next(item for item in CASES if item.path == path and item.method == "POST")
    response = api.client.post(
        PREFIX + path, content=b'{"unfinished":', headers={"Content-Type": "application/json"}
    )
    assert_error(response, 400, "INVALID_PARAMETER")
    target(api, item.target).assert_not_called()
