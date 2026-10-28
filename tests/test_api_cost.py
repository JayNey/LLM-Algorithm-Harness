"""API tests for cost tracking, budgets, alerts and pricing (issue #154)."""

import secrets
import socket
import threading
import time
from datetime import datetime
from unittest.mock import Mock, patch
from urllib.parse import quote

import httpx
import pytest
import uvicorn
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.auth.config import AuthSettings
from api.db.models import BenchmarkRun, BenchmarkSuite, Evaluation, utcnow
from api.files.config import FileSettings
from api.main import create_app


class FakeBenchmarkExecutor:
    """Deterministic benchmark executor for seeding runs."""

    def __init__(self, suite, config):
        self.suite = suite
        self.config = config

    def execute(self):
        return {
            "summary": {"accuracy": 0.8, "cost_usd": 0.2},
            "accuracy": 0.8,
            "cost_usd": 0.2,
        }


def _app_with_benchmarks(tmp_path):
    return create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        benchmark_executor_factory=FakeBenchmarkExecutor,
    )


PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"
WEBHOOK = "https://hooks.example.com/abc/secret-token"


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _signup(client, name="alice"):
    register = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.org", "password": PASSWORD},
    )
    assert register.status_code == 201, register.text
    tokens = client.post(
        "/api/v1/auth/login", json={"username": name, "password": PASSWORD}
    ).json()["data"]
    return {"Authorization": "Bearer " + tokens["access_token"]}


def _add_key(client, headers):
    return client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "test", "api_key": KEY},
    ).json()["data"]["id"]


def _completed_evaluation(client, headers, key_id, app):
    """创建并启动一次评估，然后按「队列 worker 完成后落库」的方式把行置为 completed。

    CI 无 broker/worker（与本文件 test_benchmark_run_cost_via_task_endpoint 同因），
    因此 stub send_task 后直接写回 worker 会产出的聚合状态。model 是 §5.2 起 create
    请求的必填字段。cost 端点只读 Evaluation 行的 spent_usd/completed_count/strategy_names。
    """
    created = client.post(
        "/api/v1/evaluations",
        headers=headers,
        json={
            "api_key_id": key_id,
            "model": "gpt-4o-mini",
            "problem_ids": ["p1"],
            "strategy_names": ["vanilla"],
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["data"]["evaluation_id"]
    with patch("src.task_manager.celery_app.send_task", return_value=Mock(id="fake-eval-task")):
        started = client.post(f"/api/v1/evaluations/{task_id}/start", headers=headers)
    assert started.status_code == 202, started.text

    service = app.state.evaluations
    with Session(service.engine) as session, session.begin():
        row = session.get(Evaluation, task_id)
        assert row is not None
        row.status = "completed"
        row.completed_count = len(row.problem_ids or []) * len(row.strategy_names or [])
        row.failed_count = 0
        row.spent_usd = 0.2
        row.updated_at = utcnow()

    data = client.get(f"/api/v1/evaluations/{task_id}", headers=headers).json()["data"]
    assert data["status"] == "completed", data
    return task_id, data


@pytest.fixture
def api(tmp_path):
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
    )
    with TestClient(app) as client:
        headers = _signup(client)
        key_id = _add_key(client, headers)
        yield client, headers, key_id, app


class TestCostQueries:
    def test_breakdown_preserves_saved_models(self, model_costs):
        client, headers = model_costs
        response = client.get(
            "/api/v1/costs/breakdown", headers=headers, params={"since": "2000-01-01"}
        )
        assert response.status_code == 200, response.text
        breakdown = response.json()["data"]
        assert breakdown["by_model"] == {
            "gpt-4o-mini": 0.9,
            "other-model": 0.7,
            "evaluation-run": 0.24,
        }
        assert breakdown["by_source"] == {"evaluations": 1.44, "benchmarks": 0.4}

    def test_task_cost_summary_trends_and_breakdown(self, api):
        client, headers, key_id, app = api
        task_id, view = _completed_evaluation(client, headers, key_id, app)
        assert view["spent_usd"] > 0

        task = client.get(f"/api/v1/costs/tasks/{task_id}", headers=headers)
        assert task.status_code == 200
        assert task.json()["data"]["total_cost_usd"] == view["spent_usd"]

        summary = client.get("/api/v1/costs/summary", headers=headers)
        assert summary.status_code == 200
        data = summary.json()["data"]
        assert data["total_cost_usd"] > 0
        assert data["by_source"]["evaluations"]["task_count"] == 1

        trends = client.get("/api/v1/costs/trends", headers=headers).json()["data"]
        assert len(trends["data"]) == 1
        assert trends["data"][0]["cost_usd"] > 0

        breakdown = client.get("/api/v1/costs/breakdown", headers=headers).json()["data"]
        assert breakdown["by_strategy"]["vanilla"] > 0
        assert breakdown["by_source"]["evaluations"] > 0

    def test_period_validation_and_empty_window(self, api):
        client, headers, _, _ = api
        bad = client.get("/api/v1/costs/summary", headers=headers, params={"since": "not-a-date"})
        assert bad.status_code == 400

        empty = client.get(
            "/api/v1/costs/summary",
            headers=headers,
            params={"since": "1999-01-01", "until": "1999-01-02"},
        ).json()["data"]
        assert empty["total_cost_usd"] == 0
        assert empty["task_count"] == 0

        trends = client.get(
            "/api/v1/costs/trends",
            headers=headers,
            params={"since": "1999-01-01", "until": "1999-01-02"},
        ).json()["data"]
        assert trends["data"] == []

        breakdown = client.get(
            "/api/v1/costs/breakdown",
            headers=headers,
            params={"since": "1999-01-01", "until": "1999-01-02"},
        ).json()["data"]
        assert breakdown["by_source"] == {}
        assert breakdown["by_model"] == {}
        assert breakdown["by_strategy"] == {}

        inverted = client.get(
            "/api/v1/costs/summary",
            headers=headers,
            params={"since": "2026-01-02", "until": "2026-01-01"},
        )
        assert inverted.status_code == 400

    def test_unknown_task_is_404(self, api):
        client, headers, _, _ = api
        response = client.get("/api/v1/costs/tasks/does-not-exist", headers=headers)
        assert response.status_code == 404

    def test_task_cost_is_owner_scoped(self, api):
        client, headers, key_id, app = api
        task_id, _ = _completed_evaluation(client, headers, key_id, app)
        client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.org", "password": PASSWORD},
        )
        bob = client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": PASSWORD}
        ).json()["data"]
        response = client.get(
            f"/api/v1/costs/tasks/{task_id}",
            headers={"Authorization": "Bearer " + bob["access_token"]},
        )
        assert response.status_code == 404


class TestBudgets:
    def test_upsert_get_and_usage(self, api):
        client, headers, key_id, app = api
        assert client.get("/api/v1/budgets", headers=headers).json()["data"] == {}

        _completed_evaluation(client, headers, key_id, app)
        saved = client.post(
            "/api/v1/budgets",
            headers=headers,
            json={
                "global_cap_usd": 1.0,
                "difficulty_caps": {"easy": 0.5, "medium": 0.3},
                "action": "pause",
            },
        )
        assert saved.status_code == 201, saved.text

        patched = client.patch("/api/v1/budgets", headers=headers, json={"global_cap_usd": 2.0})
        assert patched.status_code == 200
        assert patched.json()["data"]["global_cap_usd"] == 2.0

        usage = client.get("/api/v1/budgets/usage", headers=headers).json()["data"]
        assert usage["global_budget"]["cap_usd"] == 2.0
        assert usage["global_budget"]["used_usd"] > 0
        assert usage["global_budget"]["remaining_usd"] == round(
            2.0 - usage["global_budget"]["used_usd"], 6
        )
        assert usage["by_difficulty"]["easy"]["cap_usd"] == 0.5
        assert "estimate" in usage["basis"]

    def test_patch_keeps_action_and_unmentioned_fields(self, api):
        client, headers, _, _ = api
        client.post(
            "/api/v1/budgets",
            headers=headers,
            json={
                "global_cap_usd": 1.0,
                "difficulty_caps": {"easy": 0.5},
                "action": "downgrade",
            },
        )
        patched = client.patch("/api/v1/budgets", headers=headers, json={"global_cap_usd": 5.0})
        assert patched.status_code == 200
        data = patched.json()["data"]
        assert data["action"] == "downgrade"  # IMPORTANT regression: not reset to pause
        assert data["difficulty_caps"] == {"easy": 0.5}

    def test_benchmark_run_cost_via_task_endpoint(self, tmp_path):
        # Since #149 runs dispatch through celery, stub the broker send and
        # complete the run row the way the queue worker would.
        app = _app_with_benchmarks(tmp_path)

        class _FakeAsyncResult:
            id = "fake-celery-task-id"

        with patch("src.task_manager.celery_app.send_task", return_value=_FakeAsyncResult()):
            with TestClient(app) as client:
                headers = _signup(client)
                key_id = _add_key(client, headers)
                suite_id = client.post(
                    "/api/v1/benchmarks/suites",
                    headers=headers,
                    json={"name": "cost-suite", "problems": ["p1"], "frozen": False},
                ).json()["data"]["id"]
                started = client.post(
                    f"/api/v1/benchmarks/suites/{suite_id}/run",
                    headers=headers,
                    json={
                        "api_key_id": key_id,
                        "dataset_path": "problems.json",
                        "model": "bench-model",
                    },
                )
                assert started.status_code == 202, started.text
                run_id = started.json()["data"]["id"]

                from api.db import (
                    BenchmarkRun,
                    business_database_url,
                    make_engine,
                    make_session_factory,
                )
                from api.db.models import utcnow

                session_factory = make_session_factory(make_engine(business_database_url()))
                with session_factory() as session, session.begin():
                    row = session.get(BenchmarkRun, run_id)
                    assert row is not None
                    row.status = "completed"
                    row.accuracy = 0.8
                    row.cost_usd = 0.2
                    row.completed_at = utcnow()

                task = client.get(f"/api/v1/costs/tasks/{run_id}", headers=headers)
                assert task.status_code == 200
                data = task.json()["data"]
                assert data["source"] == "benchmarks"
                assert data["total_cost_usd"] == 0.2
                assert data["model"] == "bench-model"

    def test_usage_without_budget_has_caps_none(self, api):
        client, headers, _, _ = api
        usage = client.get("/api/v1/budgets/usage", headers=headers).json()["data"]
        assert usage["global_budget"]["cap_usd"] is None
        assert usage["global_budget"]["percentage_used"] is None


class TestAlertRules:
    def test_rule_crud_with_masked_target(self, api):
        client, headers, _, _ = api
        created = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={
                "name": "80pct",
                "threshold_pct": 80,
                "channel": "webhook",
                "target": WEBHOOK,
            },
        )
        assert created.status_code == 201, created.text
        rule = created.json()["data"]
        assert rule["target"] == "https://hooks.example.com/***"
        assert "secret-token" not in created.text
        rule_id = rule["id"]

        updated = client.patch(
            f"/api/v1/alerts/{rule_id}", headers=headers, json={"threshold_pct": 90}
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["threshold_pct"] == 90

        listing = client.get("/api/v1/alerts", headers=headers).json()["data"]
        assert len(listing) == 1

        history = client.get("/api/v1/alerts/history", headers=headers).json()["data"]
        assert history == []

        assert client.delete(f"/api/v1/alerts/{rule_id}", headers=headers).status_code == 204
        assert client.get("/api/v1/alerts", headers=headers).json()["data"] == []

    def test_invalid_rules_are_rejected(self, api):
        client, headers, _, _ = api
        zero = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={"threshold_pct": 0, "channel": "log"},
        )
        assert zero.status_code == 400

        unknown_channel = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={"threshold_pct": 50, "channel": "sms", "target": "x"},
        )
        assert unknown_channel.status_code == 400

        missing_target = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={"threshold_pct": 50, "channel": "webhook"},
        )
        assert missing_target.status_code == 400

    def test_cross_user_rule_access_is_404(self, api):
        client, headers, _, _ = api
        rule_id = client.post(
            "/api/v1/alerts",
            headers=headers,
            json={"threshold_pct": 50, "channel": "log"},
        ).json()["data"]["id"]
        client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.org", "password": PASSWORD},
        )
        bob = client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": PASSWORD}
        ).json()["data"]
        response = client.patch(
            f"/api/v1/alerts/{rule_id}",
            headers={"Authorization": "Bearer " + bob["access_token"]},
            json={"threshold_pct": 90},
        )
        assert response.status_code == 404


@pytest.fixture
def pricing_http(api):
    """Use a real ASGI server: TestClient can decode percent escapes twice."""
    _, headers, _, app = api
    server = uvicorn.Server(uvicorn.Config(app, lifespan="off", log_level="error", ws="none"))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            while not server.started:
                assert (
                    thread.is_alive() and time.monotonic() < deadline
                ), "HTTP server did not start"
                time.sleep(0.01)
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False) as client:
                yield client, headers
        finally:
            server.should_exit = True
            thread.join(timeout=10)
            assert not thread.is_alive(), "HTTP server did not stop"


class TestPricing:
    def test_full_model_ids_round_trip_over_http(self, pricing_http):
        client, headers = pricing_http
        models = [
            "gpt-4",
            "Qwen/Qwen2.5-7B-Instruct",
            "provider/team/model",
            "provider/history",
            "provider/history/history",
            "provider/literal%2Fmodel",
            "provider/literal/model",
            "provider/模型 +?#%",
            "a/" + "b" * 198,
        ]
        for index, model in enumerate(models, start=1):
            path = "/api/v1/pricing/" + quote(model, safe="")
            for price in (index, index + 0.5):
                response = client.post(
                    path,
                    headers=headers,
                    json={"prompt_per_1k": price, "completion_per_1k": price * 2},
                )
                assert response.status_code == 201, response.text
                assert response.json()["data"]["model"] == model

        catalog = client.get("/api/v1/pricing", headers=headers).json()["data"]["models"]
        for index, model in enumerate(models, start=1):
            assert catalog[model]["prompt_per_1k"] == index + 0.5
            assert catalog[model]["source"] == "override"
            # Both encoded and literal slashes must select exactly this model's history.
            for safe in ("", "/"):
                response = client.get(
                    "/api/v1/pricing/" + quote(model, safe=safe) + "/history", headers=headers
                )
                assert response.status_code == 200, response.text
                rows = response.json()["data"]
                assert [row["prompt_per_1k"] for row in rows] == [index + 0.5, index]
                assert all(row["created_by"] for row in rows)

    def test_full_model_id_auth_and_validation_over_http(self, pricing_http):
        client, headers = pricing_http
        path = "/api/v1/pricing/Qwen%2FQwen2.5-7B-Instruct"
        prices = {"prompt_per_1k": 1, "completion_per_1k": 2}
        assert client.post(path, json=prices).status_code == 401
        assert client.get(path + "/history").status_code == 401
        for model in ("a/" + "b" * 199, ""):
            invalid_path = "/api/v1/pricing/" + quote(model, safe="")
            assert client.post(invalid_path, headers=headers, json=prices).status_code == 400
            assert client.get(invalid_path + "/history", headers=headers).status_code == 400
        for price in (0, -1):
            assert (
                client.post(
                    path, headers=headers, json={**prices, "prompt_per_1k": price}
                ).status_code
                == 400
            )
        assert client.get(path + "/history", headers=headers).json()["data"] == []

    def test_catalog_override_and_history(self, api):
        client, headers, _, _ = api
        catalog = client.get("/api/v1/pricing", headers=headers).json()["data"]
        assert catalog["models"]["gpt-3.5-turbo"]["source"] == "builtin"

        override = client.post(
            "/api/v1/pricing/gpt-3.5-turbo",
            headers=headers,
            json={"prompt_per_1k": 0.002, "completion_per_1k": 0.003},
        )
        assert override.status_code == 201, override.text

        catalog = client.get("/api/v1/pricing", headers=headers).json()["data"]
        assert catalog["models"]["gpt-3.5-turbo"]["source"] == "override"
        assert catalog["models"]["gpt-3.5-turbo"]["prompt_per_1k"] == 0.002

        client.post(
            "/api/v1/pricing/gpt-3.5-turbo",
            headers=headers,
            json={"prompt_per_1k": 0.004, "completion_per_1k": 0.006},
        )
        history = client.get("/api/v1/pricing/gpt-3.5-turbo/history", headers=headers).json()[
            "data"
        ]
        assert len(history) == 2
        assert history[0]["prompt_per_1k"] == 0.004  # latest first

    def test_nonpositive_prices_rejected(self, api):
        client, headers, _, _ = api
        response = client.post(
            "/api/v1/pricing/gpt-x",
            headers=headers,
            json={"prompt_per_1k": 0, "completion_per_1k": 1},
        )
        assert response.status_code == 400


class TestReports:
    def test_optimization_groups_by_saved_model_and_strategy(self, model_costs):
        client, headers = model_costs
        response = client.get("/api/v1/reports/cost-optimization", headers=headers)
        assert response.status_code == 200, response.text
        ranking = response.json()["data"]["ranking"]["ranking"]
        rows = {(row["model"], row["strategy"]): row for row in ranking}
        assert len(ranking) == len(rows) == 5
        assert rows[("gpt-4o-mini", "vanilla")]["cost_usd"] == 0.5
        assert rows[("gpt-4o-mini", "vanilla")]["accuracy"] == 0.5
        assert rows[("other-model", "vanilla")]["cost_usd"] == 0.7
        assert rows[("other-model", "vanilla")]["accuracy"] == 0
        assert rows[("evaluation-run", "vanilla")]["cost_usd"] == 0.24
        assert rows[("gpt-4o-mini", "benchmark")]["cost_usd"] == 0.4
        assert rows[("old-model", "vanilla")]["cost_usd"] == 0.8

    def test_task_report_and_optimization(self, api):
        client, headers, key_id, app = api
        task_id, _ = _completed_evaluation(client, headers, key_id, app)

        report = client.get(f"/api/v1/reports/cost/{task_id}", headers=headers)
        assert report.status_code == 200
        assert report.json()["data"]["total_cost_usd"] > 0

        optimization = client.get("/api/v1/reports/cost-optimization", headers=headers).json()[
            "data"
        ]
        assert "ranking" in optimization
        ranked = optimization["ranking"]["ranking"]
        assert ranked and ranked[0]["cost_usd"] > 0


@pytest.fixture
def model_costs(api):
    """Mix saved model names, legacy rows and benchmark spend without a worker."""
    client, headers, key_id, app = api
    task_id, _ = _completed_evaluation(client, headers, key_id, app)
    with Session(app.state.evaluations.engine) as session, session.begin():
        owner_id = session.get(Evaluation, task_id).user_id
        session.add(BenchmarkSuite(id="cost-suite", name="Cost suite", user_id=owner_id))
        session.flush()
        for row_id, model, cost, completed in [
            ("same-model", "gpt-4o-mini", 0.3, 0),
            ("other-model", "other-model", 0.7, 0),
            ("legacy-null", None, 0.11, 1),
            ("legacy-empty", "", 0.13, 1),
        ]:
            session.add(
                Evaluation(
                    id=row_id,
                    user_id=owner_id,
                    model=model,
                    status="completed",
                    strategy_names=["vanilla"],
                    problem_count=1,
                    completed_count=completed,
                    spent_usd=cost,
                )
            )
        session.add_all(
            [
                BenchmarkRun(
                    id="benchmark",
                    suite_id="cost-suite",
                    user_id=owner_id,
                    model="gpt-4o-mini",
                    status="completed",
                    cost_usd=0.4,
                    accuracy=0.8,
                ),
                Evaluation(
                    id="foreign",
                    user_id="another-owner",
                    model="foreign-model",
                    status="completed",
                    strategy_names=["vanilla"],
                    problem_count=1,
                    completed_count=1,
                    spent_usd=99,
                ),
                Evaluation(
                    id="old",
                    user_id=owner_id,
                    model="old-model",
                    status="completed",
                    strategy_names=["vanilla"],
                    problem_count=1,
                    completed_count=1,
                    spent_usd=0.8,
                    created_at=datetime(1999, 1, 1),
                ),
            ]
        )
    return client, headers


@pytest.mark.parametrize(
    "action,want_status,strategies",
    [
        ("pause", "paused", ["chain_of_thought"]),
        ("downgrade", "completed", ["chain_of_thought", "vanilla"]),
    ],
)
def test_web_saved_budget_controls_worker(
    api, monkeypatch, tmp_path, action, want_status, strategies
):
    """The HTTP write must govern real TaskService dispatch, not just budget display."""
    from api.db.models import EvaluationResult, Problem
    from src.harness import AlgorithmHarness
    from src.models import ExecutionResult
    from src.tasks.evaluation import run_evaluation_task

    client, headers, key_id, app = api
    monkeypatch.chdir(tmp_path)
    calls = []
    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", lambda *_: (None, None))

    def execute(_self, config, problem, *_):
        calls.append(config.name)
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=config.name,
            generated_code="def solution(): return 1",
            status="success",
            difficulty=problem.difficulty,
        )

    monkeypatch.setattr(AlgorithmHarness, "_execute_problem", execute)
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", lambda *_: (0.01, {}))
    monkeypatch.setattr("api.auth.config.AuthSettings", lambda: app.state.auth.settings)
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda **_: None)
    monkeypatch.setattr("src.tasks.evaluation.publish_progress", lambda *_: True)
    with app.state.evaluations._session() as db, db.begin():
        for pid in ("budget-p1", "budget-p2"):
            db.add(
                Problem(
                    id=pid,
                    problem_id=pid,
                    title=pid,
                    description="Return the constant integer one.",
                    difficulty="easy",
                    tags=[],
                    test_cases=[{"input": {}, "expected_output": 1}],
                )
            )
    saved = client.post(
        "/api/v1/budgets", headers=headers, json={"global_cap_usd": 0.01, "action": action}
    )
    assert saved.status_code in (200, 201), saved.text
    rule = client.post(
        "/api/v1/alerts",
        headers=headers,
        json={"threshold_pct": 100, "channel": "webhook", "target": WEBHOOK},
    )
    assert rule.status_code == 201, rule.text
    deliveries = []

    def post_alert(url, **kwargs):
        deliveries.append((url, kwargs["json"]))
        return Mock(status_code=200, raise_for_status=lambda: None)

    monkeypatch.setattr("src.cost_alert.requests.post", post_alert)
    created = client.post(
        "/api/v1/evaluations",
        headers=headers,
        json={
            "api_key_id": key_id,
            "model": "test",
            "strategy_names": ["chain_of_thought"],
            "problem_ids": ["budget-p1", "budget-p2"],
        },
    )
    assert created.status_code == 201, created.text
    evaluation_id = created.json()["data"]["evaluation_id"]
    with patch("src.task_manager.celery_app.send_task", return_value=Mock(id="budget-celery")):
        assert (
            client.post(f"/api/v1/evaluations/{evaluation_id}/start", headers=headers).status_code
            == 202
        )
    monkeypatch.setattr("src.tasks.evaluation.get_db_session", app.state.evaluations._session)
    assert run_evaluation_task(evaluation_id)["status"] == want_status
    assert calls == strategies
    view = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers).json()["data"]
    assert view["status"] == want_status
    with app.state.evaluations._session() as db:
        rows = db.query(EvaluationResult).filter_by(evaluation_id=evaluation_id).all()
        assert len(rows) == len(strategies)
    usage = client.get("/api/v1/budgets/usage", headers=headers).json()["data"]
    assert usage["global_budget"]["used_usd"] == pytest.approx(0.01 * len(strategies))

    assert len(deliveries) == 1
    assert deliveries[0][0] == WEBHOOK
    assert deliveries[0][1]["accumulated_cost_usd"] == 0.01
    history = client.get("/api/v1/alerts/history", headers=headers).json()["data"]
    assert len(history) == 1
    assert history[0]["rule_id"] == rule.json()["data"]["id"]


def test_experiment_ab_accounting_same_scope_across_all_cost_views(api):
    """Call rows must flow through HTTP without double-counting tasks or old sources."""
    from api.db.models import ABTest, Budget, Experiment, SpendRecord

    client, headers, _key_id, app = api
    owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id
    with app.state.cost._session() as db, db.begin():
        db.add_all(
            [
                Experiment(id="cost-exp", user_id=owner, status="paused", config={}),
                ABTest(id="cost-ab", user_id=owner, status="failed", config={}),
                Budget(
                    id="budget",
                    user_id=owner,
                    global_cap_usd=10,
                    difficulty_caps={"easy": 0.5},
                    action="pause",
                ),
                Evaluation(
                    id="cost-eval",
                    user_id=owner,
                    status="completed",
                    spent_usd=0.4,
                    created_at=datetime(2026, 10, 2),
                ),
            ]
        )
        db.add_all(
            [
                SpendRecord(
                    id="exp-call1",
                    source="experiments",
                    task_id="cost-exp",
                    user_id=owner,
                    occurred_at=datetime(2026, 10, 2, 10),
                    model="model-a",
                    strategy="vanilla",
                    cost_usd=0.2,
                    difficulty="easy",
                ),
                SpendRecord(
                    id="exp-call2",
                    source="experiments",
                    task_id="cost-exp",
                    user_id=owner,
                    occurred_at=datetime(2026, 10, 2, 23, 59, 59),
                    model="model-a",
                    strategy="vanilla",
                    cost_usd=0.3,
                    difficulty="easy",
                ),
                SpendRecord(
                    id="ab-call",
                    source="ab_tests",
                    task_id="cost-ab",
                    user_id=owner,
                    occurred_at=datetime(2026, 10, 2, 12),
                    model="model-b",
                    strategy="reflexion",
                    cost_usd=0.6,
                ),
                SpendRecord(
                    id="next-day",
                    source="ab_tests",
                    task_id="cost-ab",
                    user_id=owner,
                    occurred_at=datetime(2026, 10, 3),
                    model="model-b",
                    strategy="reflexion",
                    cost_usd=1,
                ),
                SpendRecord(
                    id="foreign",
                    source="experiments",
                    task_id="cost-exp",
                    user_id="other",
                    occurred_at=datetime(2026, 10, 2),
                    model="model-a",
                    strategy="vanilla",
                    cost_usd=99,
                ),
            ]
        )

    def get(path):
        result = client.get("/api/v1/" + path, headers=headers)
        assert result.status_code == 200, result.text
        return result.json()["data"]

    exp = get("costs/tasks/cost-exp")
    assert exp["total_cost_usd"] == 0.5
    assert exp["cost_complete"] is True
    assert get("reports/cost/cost-exp")["total_cost_usd"] == 0.5
    period = "?since=2026-10-02&until=2026-10-02"
    summary = get("costs/summary" + period)
    assert summary["total_cost_usd"] == 1.5
    assert summary["task_count"] == 3
    assert summary["by_source"]["experiments"]["task_count"] == 1
    assert summary["by_source"]["ab_tests"]["cost_usd"] == 0.6
    assert get("costs/trends" + period)["data"][0]["cost_usd"] == 1.5
    assert sum(get("costs/breakdown" + period)["by_source"].values()) == pytest.approx(1.5)
    assert get("costs/summary?since=2026-10-03T00:00:00%2B00:00")["total_cost_usd"] == 1
    assert get("costs/summary")["total_cost_usd"] == 2.5
    usage = get("budgets/usage")
    assert usage["global_budget"]["used_usd"] == 2.5
    assert usage["by_difficulty"]["easy"]["used_usd"] == 0.5
    with app.state.cost._session() as db:
        execution = app.state.cost.execution_budget(db, owner)
        assert float(execution["used_usd"]) == 2.5
        assert execution["exhausted_difficulties"] == ["easy"]


def test_unknown_experiment_cost_is_partial_and_legacy_is_never_free(api):
    from api.db.models import ABTest, Experiment, SpendRecord

    client, headers, _key_id, app = api
    owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id
    with app.state.cost._session() as db, db.begin():
        db.add_all(
            [
                Experiment(id="partial", user_id=owner, status="cancelled", config={}),
                ABTest(
                    id="legacy",
                    user_id=owner,
                    status="completed",
                    config={},
                    cost_tracking_complete=False,
                ),
                ABTest(id="unknown", user_id=owner, status="failed", config={}),
            ]
        )
        db.add_all(
            [
                SpendRecord(
                    id="known",
                    source="experiments",
                    task_id="partial",
                    user_id=owner,
                    model="m",
                    strategy="s",
                    cost_usd=0.2,
                ),
                SpendRecord(
                    id="unpriced",
                    source="experiments",
                    task_id="partial",
                    user_id=owner,
                    model="m",
                    strategy="s",
                    cost_usd=None,
                    unknown_reason="missing_pricing",
                ),
                SpendRecord(
                    id="no-usage",
                    source="ab_tests",
                    task_id="unknown",
                    user_id=owner,
                    model="m",
                    strategy="s",
                    cost_usd=None,
                    unknown_reason="missing_usage",
                ),
            ]
        )
    partial = client.get("/api/v1/costs/tasks/partial", headers=headers).json()["data"]
    assert partial["total_cost_usd"] == 0.2
    assert partial["known_cost_usd"] == 0.2
    assert partial["cost_complete"] is False
    assert partial["unknown_cost_count"] == 1
    for job in ("legacy", "unknown"):
        result = client.get(f"/api/v1/costs/tasks/{job}", headers=headers).json()["data"]
        assert result["total_cost_usd"] is None
        assert result["cost_complete"] is False
    summary = client.get("/api/v1/costs/summary", headers=headers).json()["data"]
    assert summary["total_cost_usd"] == 0.2
    assert summary["unknown_cost_count"] == 3
    assert set(summary["unknown_reasons"]) == {"historical_gap", "missing_usage", "missing_pricing"}


@pytest.mark.parametrize("kind", ["experiment", "ab"])
def test_real_worker_spend_reaches_http_during_pause_resume_and_duplicate_delivery(
    api, pricing_http, tmp_path, monkeypatch, kind
):
    """Only provider SDK/broker replaced; real runners, database and HTTP."""
    import json
    from types import SimpleNamespace

    from api.config import settings
    from api.db.models import AsyncTask
    from src.ab_testing import ABTestRunner
    from src.experiment import ExperimentRunner
    from src.llm_client import LLMClient
    from src.models import SandboxConfig
    from src.tasks.ab_test import run_ab_test_task
    from src.tasks.experiment import run_experiment_task

    _, headers, key_id, app = api
    http, _ = pricing_http
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    (tmp_path / "problems.json").write_text(
        json.dumps(
            [
                {
                    "problem_id": f"p{i}",
                    "title": "Plus one",
                    "description": "Return the input integer plus one.",
                    "difficulty": "easy",
                    "tags": [],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
                for i in range(2)
            ]
        ),
        encoding="utf-8",
    )

    def create(**_kwargs):
        return SimpleNamespace(
            model="priced/model",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```python\ndef solution(x): return x + 1\n```"
                    ),
                    finish_reason="stop",
                )
            ],
        )

    monkeypatch.setattr(
        LLMClient,
        "_initialize_client",
        lambda _: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            base_url="https://provider.invalid/v1",
        ),
    )
    price = http.post(
        "/api/v1/pricing/priced%2Fmodel",
        headers=headers,
        json={"prompt_per_1k": 1, "completion_per_1k": 4},
    )
    assert price.status_code == 201, price.text
    paused_once, observed = [], []
    job_id = task_id = None

    def pause_after_unit():
        if paused_once:
            return
        paused_once.append(True)
        result = http.get(f"/api/v1/costs/tasks/{job_id}", headers=headers).json()["data"]
        observed.append(result["total_cost_usd"])
        with patch("src.task_manager.TaskManager._sync_celery_state"):
            paused = http.post(f"/api/v1/tasks/{task_id}/pause", headers=headers)
        assert paused.status_code == 200, paused.text

    class PausingExperiment(ExperimentRunner):
        def run(self):
            original = self.on_combination

            def progress(current, *args):
                if current == 1:
                    pause_after_unit()
                if original is not None:
                    original(current, *args)

            self.on_combination = progress
            return super().run()

    class PausingAB(ABTestRunner):
        def run(self):
            original = self.on_problem

            def progress(current, *args):
                if current == 1:
                    pause_after_unit()
                if original is not None:
                    original(current, *args)

            self.on_problem = progress
            return super().run()

    if kind == "experiment":
        service = app.state.experiments

        def factory(config):
            config.sandbox_config = SandboxConfig(backend="host")
            config.models = [
                m.model_copy(update={"cache": m.cache.model_copy(update={"enabled": False})})
                for m in config.models
            ]
            return PausingExperiment(config)

        service._runner_factory = factory
        monkeypatch.setattr("src.experiment.generate_comparison_report", lambda _: None)
        monkeypatch.setattr("src.experiment.generate_html_panel", lambda _: None)
        monkeypatch.setattr("src.tasks.experiment.get_db_session", service._session)
        monkeypatch.setattr("src.tasks.experiment.execute_experiment", service._execute)
        worker = run_experiment_task
        path = "experiments"
        payload = {
            "dataset_path": "problems.json",
            "api_key_id": key_id,
            "models": [{"model": "priced/model"}],
            "strategies": [{"name": "vanilla"}],
            "repeats": 2,
        }
        partial_cost, final_cost = 0.6, 1.2
    else:
        service = app.state.ab_tests

        def factory(config):
            config.sandbox_config = SandboxConfig(backend="host")
            config.model = config.model.model_copy(
                update={"cache": config.model.cache.model_copy(update={"enabled": False})}
            )
            return PausingAB(config)

        service._runner_factory = factory
        monkeypatch.setattr("api.services.ab_test_service.ABTestService", lambda **_: service)
        worker = run_ab_test_task
        path = "ab-tests"
        payload = {
            "dataset_path": "problems.json",
            "api_key_id": key_id,
            "model": {"model": "priced/model"},
            "strategy": {"name": "vanilla"},
            "prompt_variants": [{"id": "a"}, {"id": "b"}],
        }
        partial_cost, final_cost = 0.3, 0.6
    created = http.post(f"/api/v1/{path}", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    job_id = created.json()["data"]["id"]
    with patch("src.task_manager.celery_app.send_task"):
        started = http.post(f"/api/v1/{path}/{job_id}/run", headers=headers)
    assert started.status_code == 202, started.text
    task_id = started.json()["data"]["task_id"]
    owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id
    assert worker(job_id, owner)["status"] == "paused"
    assert observed == [partial_cost]
    result = http.get(f"/api/v1/reports/cost/{job_id}", headers=headers).json()["data"]
    assert result["status"] == "paused"
    assert result["total_cost_usd"] == partial_cost
    assert result["cost_complete"] is True
    with patch("src.task_manager.celery_app.send_task"):
        resumed = http.post(f"/api/v1/tasks/{task_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert worker(job_id, owner)["status"] == "completed"
    assert worker(job_id, owner)["status"] == "completed"
    summary = http.get("/api/v1/costs/summary", headers=headers).json()["data"]
    assert summary["total_cost_usd"] == final_cost
    assert summary["task_count"] == 1
    assert (
        http.get("/api/v1/budgets/usage", headers=headers).json()["data"]["global_budget"][
            "used_usd"
        ]
        == final_cost
    )
    with service._session() as db:
        assert db.get(AsyncTask, task_id).status == "completed"
