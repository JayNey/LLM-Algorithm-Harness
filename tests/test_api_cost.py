"""API tests for cost tracking, budgets, alerts and pricing (issue #154)."""

import secrets
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
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


class TestPricing:
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
