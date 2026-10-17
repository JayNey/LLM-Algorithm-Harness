"""API tests for owner-scoped evaluation result queries."""

import secrets
import uuid
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.auth.config import AuthSettings
from api.db.engine import make_engine, make_session_factory
from api.db.models import Evaluation, EvaluationResult, Problem
from api.files.config import FileSettings
from api.main import create_app

PASSWORD = "a-long-test-password-!"


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _seed(database_url: str, owner_id: str) -> None:
    """Insert the two Task 2 evaluations into the app's business database."""
    session_factory = make_session_factory(make_engine(database_url))
    with session_factory() as db:
        db.add(
            Problem(
                id="p1",
                problem_id="two-sum",
                title="Two Sum",
                difficulty="easy",
                tags=["array"],
            )
        )
        db.add_all(
            [
                Evaluation(
                    id="eval-own",
                    user_id=owner_id,
                    run_id="run-own",
                    status="completed",
                    strategy_names=["vanilla", "retry"],
                    problem_ids=["two-sum"],
                    model="gpt-test",
                    created_at=datetime(2026, 10, 1, 0, 0, 0),
                    completed_at=datetime(2026, 10, 1, 1, 0, 0),
                ),
                Evaluation(
                    id="eval-other",
                    user_id="other",
                    run_id="run-other",
                    status="completed",
                    strategy_names=["vanilla"],
                    problem_ids=["two-sum"],
                    model="gpt-test",
                ),
            ]
        )
        db.add_all(
            [
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 10,
                        "execution_time_seconds": 1.0,
                        "cost_usd": 0.2,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 1,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="retry",
                    status="failed",
                    metrics={
                        "success": False,
                        "total_tokens": 30,
                        "execution_time_seconds": 3.0,
                        "cost_usd": 9.0,
                        "cost_unknown": True,
                        "difficulty": "easy",
                    },
                    error_message="boom",
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-other",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "iterations": 1,
                        "total_tokens": 1,
                        "cost_usd": 1,
                        "cost_unknown": False,
                    },
                ),
            ]
        )
        db.commit()


@pytest.fixture
def results_api(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'biz.sqlite3'}"
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        database_url=database_url,
    )
    with TestClient(app) as test_client:
        register = test_client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
        )
        assert register.status_code == 201, register.text
        tokens = test_client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
        ).json()["data"]
        headers = {"Authorization": "Bearer " + tokens["access_token"]}
        _seed(database_url, register.json()["data"]["id"])
        yield test_client, headers


@pytest.fixture
def client(results_api):
    return results_api[0]


@pytest.fixture
def owner_headers(results_api):
    return results_api[1]


def _install_analytics_rows(client) -> None:
    """Replace run-own with 3 successes and 1 historical failure.

    One success costs 0.2 USD. Another success is cost_unknown with cost_usd 9.
    The failure omits metrics.iterations. A running evaluation of the same user
    must stay outside the completed-only scope.
    """
    session_factory = client.app.state.task_session_factory
    with session_factory() as db:
        owner = db.scalar(select(Evaluation).where(Evaluation.id == "eval-own"))
        assert owner is not None
        stored = list(
            db.scalars(
                select(EvaluationResult).where(EvaluationResult.evaluation_id == "eval-own")
            ).all()
        )
        for row in stored:
            db.delete(row)
        db.add(
            Evaluation(
                id="eval-open",
                user_id=owner.user_id,
                run_id="run-open",
                status="running",
                strategy_names=["vanilla"],
                problem_ids=["two-sum"],
                model="gpt-test",
            )
        )
        db.add_all(
            [
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 10,
                        "execution_time_seconds": 1.0,
                        "cost_usd": 0.2,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 1,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="retry",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 20,
                        "execution_time_seconds": 2.0,
                        "cost_usd": 9,
                        "cost_unknown": True,
                        "difficulty": "easy",
                        "iterations": 2,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="reflect",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 30,
                        "execution_time_seconds": 3.0,
                        "cost_usd": 0,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 3,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="failed",
                    metrics={
                        "success": False,
                        "total_tokens": 40,
                        "execution_time_seconds": 4.0,
                        "difficulty": "easy",
                    },
                    error_message="boom",
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-open",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 1,
                        "execution_time_seconds": 9.0,
                        "cost_usd": 5,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 9,
                    },
                ),
            ]
        )
        db.commit()


def test_analytics_match_stored_rows(client, owner_headers):
    _install_analytics_rows(client)
    rate = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert rate.status_code == 200
    assert rate.json()["data"]["success_rate"] == 0.75
    assert rate.json()["data"]["solved"] == 3
    assert rate.json()["data"]["total"] == 4
    assert rate.json()["data"]["avg_execution_time"] == 2.5
    assert rate.json()["data"]["by_difficulty"] == {
        "easy": {"success_rate": 0.75, "solved": 3, "total": 4}
    }
    assert rate.json()["data"]["by_tag"] == {
        "array": {"success_rate": 0.75, "solved": 3, "total": 4}
    }
    scoped = client.get("/api/v1/analytics/success-rate", headers=owner_headers)
    assert scoped.status_code == 200
    assert scoped.json()["data"]["solved"] == 3
    assert scoped.json()["data"]["total"] == 4
    running = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-open"}
    )
    assert running.status_code == 200
    assert running.json()["data"]["solved"] == 1
    assert running.json()["data"]["total"] == 1
    missing = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-other"}
    )
    assert missing.status_code == 404
    tokens = client.get(
        "/api/v1/analytics/tokens", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert tokens.json()["data"]["total_tokens"] == 100
    assert tokens.json()["data"]["avg_tokens"] == 25
    assert tokens.json()["data"]["estimated_cost_usd"] == 0.2
    assert tokens.json()["data"]["unknown_cost_count"] == 1
    modes = client.get(
        "/api/v1/analytics/failure-modes", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert modes.status_code == 200
    assert modes.json()["data"] == {"unknown": 1}
    iterations = client.get(
        "/api/v1/analytics/iterations", headers=owner_headers, params={"run_id": "run-own"}
    )
    payload = iterations.json()["data"]
    assert payload["average"] == 2
    assert payload["distribution"] == [
        {"iterations": 1, "count": 1},
        {"iterations": 2, "count": 1},
        {"iterations": 3, "count": 1},
    ]
    assert payload["unknown_count"] == 1
    assert payload["known_count"] == 3


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
