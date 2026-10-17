"""API tests for owner-scoped evaluation result queries."""

import secrets
import uuid
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

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
