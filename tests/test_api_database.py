"""Business database tests for issue #151: migrations, problem import and evaluation persistence."""

import secrets
import time

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from api.auth.config import AuthSettings
from api.db import (
    ProblemStore,
    downgrade,
    make_engine,
    make_session_factory,
    offline_upgrade_sql,
    run_migrations,
)
from api.files.config import FileSettings
from api.main import create_app
from api.models import EvaluationCreateRequest
from api.services.evaluation_service import EvaluationService

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"
RESTART_REASON = "interrupted by service restart"


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _bootstrap_user(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
    ).json()["data"]
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    key_id = client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "test", "api_key": KEY},
    ).json()["data"]["id"]
    return headers, key_id


def _wait_for_status(service, evaluation_id, owner_id, statuses, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = service.get_evaluation(evaluation_id, owner_id)
        if response.status in statuses:
            return response
        time.sleep(0.05)
    pytest.fail(f"evaluation did not reach {statuses} in time: {response.status}")


class TestMigrations:
    def test_roundtrip_on_empty_database(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'migrate.sqlite3'}"

        run_migrations(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert {"problems", "evaluations", "evaluation_results"} <= tables

        downgrade(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert not tables & {"problems", "evaluations", "evaluation_results"}

        run_migrations(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert {"problems", "evaluations", "evaluation_results"} <= tables

    def test_upgrade_sql_is_portable_to_postgresql(self):
        sql = offline_upgrade_sql("postgresql://user:pass@localhost:5432/business")
        assert "CREATE TABLE problems" in sql
        assert "CREATE TABLE evaluations" in sql
        assert "CREATE TABLE evaluation_results" in sql
        assert "ON DELETE CASCADE" in sql
        assert "sqlite" not in sql.lower()


class TestProblemStore:
    @pytest.fixture
    def store(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'problems.sqlite3'}"
        run_migrations(url)
        return ProblemStore(make_session_factory(make_engine(url)))

    def test_reimport_updates_in_place_without_duplicates(self, store):
        first = {"problem_id": "two-sum", "title": "Two Sum", "tags": ["array"]}
        second = {"problem_id": "two-sum", "title": "Two Sum v2", "tags": ["array", "hash"]}

        assert store.upsert_import([first]) == 1
        assert store.upsert_import([second]) == 1

        assert store.count() == 1
        problem = store.get_by_problem_id("two-sum")
        assert problem.title == "Two Sum v2"
        assert problem.tags == ["array", "hash"]

    def test_import_json_file_is_repeatable(self, store):
        assert store.import_json_file("data/problems.json") == 12
        assert store.import_json_file("data/problems.json") == 12
        assert store.count() == 12
        assert store.get_by_problem_id("two-sum") is not None

    def test_record_without_problem_id_is_rejected(self, store):
        with pytest.raises(ValueError, match="problem_id"):
            store.upsert_import([{"title": "no id"}])


class TestEvaluationPersistence:
    def test_restart_marks_non_terminal_tasks_failed(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            created = client.post(
                "/api/v1/evaluations",
                headers=headers,
                json={
                    "api_key_id": key_id,
                    "problem_ids": ["two-sum"],
                    "strategy_names": ["cot"],
                },
            )
            assert created.status_code == 201, created.text
            task_id = created.json()["data"]["evaluation_id"]

        # A fresh process against the same database observes the task...
        revived = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(revived) as client:
            headers, _ = _bootstrap_user(client)
            data = client.get(f"/api/v1/evaluations/{task_id}", headers=headers).json()["data"]
            assert data["status"] == "failed"
            assert data["error_message"] == RESTART_REASON

    def test_completed_results_survive_restart(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1"], strategy_names=["cot"]
        )
        created = service.create_evaluation(request, "alice")
        started = service.start_evaluation(created.evaluation_id, "alice")
        assert started.status == "running"

        finished = _wait_for_status(service, created.evaluation_id, "alice", {"completed"})
        assert finished.progress.completed == 1
        assert finished.spent_usd > 0

        revived = EvaluationService(url)
        after = revived.get_evaluation(created.evaluation_id, "alice")
        assert after.status == "completed"
        assert after.progress.completed == 1
        assert after.spent_usd == finished.spent_usd

    def test_rows_are_owner_scoped(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1"], strategy_names=["cot"]
        )
        created = service.create_evaluation(request, "alice")

        assert service.get_evaluation(created.evaluation_id, "alice").status == "pending"
        with pytest.raises(ValueError, match="not found"):
            service.get_evaluation(created.evaluation_id, "bob")

    def test_cancelled_task_stays_cancelled_after_executor_exits(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1", "p2"], strategy_names=["cot"]
        )
        created = service.create_evaluation(request, "alice")
        service.start_evaluation(created.evaluation_id, "alice")

        cancelled = service.cancel_evaluation(created.evaluation_id, "alice")
        assert cancelled.status == "cancelled"

        finished = _wait_for_status(
            service, created.evaluation_id, "alice", {"cancelled"}, timeout=3.0
        )
        assert finished.status == "cancelled"
