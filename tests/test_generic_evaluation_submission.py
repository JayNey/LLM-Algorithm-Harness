"""Generic evaluation submission must produce an owned, executable business task."""

import secrets
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.auth.config import AuthSettings
from api.auth.dependencies import current_user
from api.auth.models import KeyCreate
from api.auth.service import AuthService, Principal
from api.config import settings
from api.db.engine import get_db
from api.db.models import AsyncTask, Evaluation, EvaluationResult, Problem
from api.files.config import FileSettings
from api.files.service import FileService
from api.middleware.errors import setup_error_handlers
from api.routes.evaluations import router as evaluations_router
from api.routes.tasks import router as tasks_router
from api.services.evaluation_service import EvaluationService
from src.harness import AlgorithmHarness
from src.models import ExecutionResult
from src.task_manager import celery_app
from src.tasks.evaluation import run_evaluation_task


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("ENCRYPTION_KEY", Fernet.generate_key().decode())
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(tmp_path / "auth.sqlite3"))
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    auth = AuthService(AuthSettings(_env_file=None))
    for owner in ("alice", "bob"):
        auth.store.add_user(owner, owner, f"{owner}@example.org", "unused-password-hash")
    key = auth.add_key(
        "alice", KeyCreate(provider="openai", key_name="test", api_key="sk-test-only")
    )["id"]
    service = EvaluationService(f"sqlite:///{tmp_path / 'business.sqlite3'}")
    app = FastAPI()
    setup_error_handlers(app)
    app.state.auth = auth
    app.state.evaluations = service
    app.state.files = FileService(auth, FileSettings(_env_file=None))
    app.include_router(evaluations_router)
    app.include_router(tasks_router)
    app.dependency_overrides[current_user] = lambda: Principal("alice", "session-alice")

    def database():
        with service._session() as session:
            yield session

    app.dependency_overrides[get_db] = database
    publisher = Mock(return_value=SimpleNamespace(id="ignored-broker-id"))
    audit_events = []
    auth.audit_sink = lambda *event: audit_events.append(event)
    monkeypatch.setattr(celery_app, "send_task", publisher)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/evaluations",
            json=dict(
                api_key_id=key,
                model="gpt-4o-mini",
                problem_ids=["p1"],
                strategy_names=["vanilla"],
            ),
        )
        assert response.status_code == 201, response.text
        yield SimpleNamespace(
            client=client,
            service=service,
            auth=auth,
            key=key,
            evaluation_id=response.json()["data"]["evaluation_id"],
            publisher=publisher,
            audit_events=audit_events,
        )
    service.close()


def submit(api, **overrides):
    body = dict(
        task_type="evaluation",
        entity_id=api.evaluation_id,
        celery_task_name="src.tasks.evaluation.run_evaluation_task",
    )
    body.update(overrides)
    return api.client.post("/api/v1/tasks", json=body)


def assert_rejected(api, response, status):
    assert response.status_code == status, response.text
    with api.service._session() as session:
        assert session.scalar(select(AsyncTask)) is None
        assert session.get(Evaluation, api.evaluation_id).async_task_id is None
    api.publisher.assert_not_called()


@pytest.mark.parametrize("args", [None, [], ["same-entity"]])
def test_owned_draft_has_committed_link_before_publication(api, args):
    seen = []

    def publish(name, *, args, kwargs, task_id):
        with api.service._session() as session:
            evaluation = session.get(Evaluation, api.evaluation_id)
            assert evaluation.async_task_id is not None
            task = session.get(AsyncTask, evaluation.async_task_id)
            assert task is not None
            assert (task.entity_id, task.user_id, task.status) == (
                api.evaluation_id,
                "alice",
                "pending",
            )
            assert task.celery_task_id == task_id
            assert args == (api.evaluation_id,)
            assert kwargs == {}
            seen.append(task.id)

    api.publisher.side_effect = publish
    response = submit(
        api, celery_task_args=[api.evaluation_id] if args == ["same-entity"] else args
    )
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert seen == [data["id"]]
    assert data["status"] == "pending"
    assert data["entity_id"] == api.evaluation_id
    assert api.audit_events.count(("evaluation_start", "alice", api.evaluation_id)) == 1


@pytest.mark.parametrize("entity", ["missing", "foreign"])
def test_missing_or_foreign_evaluation_is_rejected(api, entity):
    if entity == "foreign":
        with api.service._session() as session, session.begin():
            session.get(Evaluation, api.evaluation_id).user_id = "bob"
    assert_rejected(
        api, submit(api, entity_id="missing" if entity == "missing" else api.evaluation_id), 404
    )


@pytest.mark.parametrize("status", ["running", "paused", "completed", "failed", "cancelled"])
def test_non_pending_evaluation_is_rejected(api, status):
    with api.service._session() as session, session.begin():
        session.get(Evaluation, api.evaluation_id).status = status
    assert_rejected(api, submit(api), 400)


@pytest.mark.parametrize(
    "overrides",
    [
        {"celery_task_args": ["another-evaluation"]},
        {"celery_task_args": ["same-entity", "alice"]},
        {"celery_task_kwargs": {"evaluation_id": "another-evaluation"}},
        {"celery_task_kwargs": {"user_id": "bob"}},
    ],
)
def test_untrusted_execution_parameters_are_rejected(api, overrides):
    assert_rejected(api, submit(api, **overrides), 400)


@pytest.mark.parametrize("credential", ["missing", "foreign"])
def test_unavailable_credential_is_rejected(api, credential):
    if credential == "missing":
        api.auth.delete_key(api.key, "alice")
    else:
        key = api.auth.add_key(
            "bob", KeyCreate(provider="openai", key_name="other", api_key="sk-other-test")
        )["id"]
        with api.service._session() as session, session.begin():
            session.get(Evaluation, api.evaluation_id).api_key_id = key
    assert_rejected(api, submit(api), 404)


def test_repeated_submission_preserves_original_task(api):
    first = submit(api)
    assert first.status_code == 201, first.text
    second = submit(api)
    assert second.status_code == 400, second.text
    with api.service._session() as session:
        tasks = session.scalars(select(AsyncTask)).all()
        assert [task.id for task in tasks] == [first.json()["data"]["id"]]
        assert session.get(Evaluation, api.evaluation_id).async_task_id == tasks[0].id
    assert api.publisher.call_count == 1


def test_capacity_rejection_preserves_draft(api, monkeypatch):
    monkeypatch.setattr(settings, "MAX_CONCURRENT_EVALUATIONS_PER_USER", 1)
    with api.service._session() as session, session.begin():
        session.add(
            AsyncTask(
                id="existing",
                celery_task_id="existing-celery",
                task_type="evaluation",
                entity_id="another",
                user_id="alice",
                status="pending",
            )
        )
    response = submit(api)
    assert response.status_code == 429, response.text
    assert response.json()["error"]["code"] == "QUOTA_EXCEEDED"
    with api.service._session() as session:
        assert [task.id for task in session.scalars(select(AsyncTask))] == ["existing"]
        assert session.get(Evaluation, api.evaluation_id).async_task_id is None
    api.publisher.assert_not_called()


def test_broker_failure_is_recorded_and_draft_can_retry(api):
    api.publisher.side_effect = RuntimeError("broker unavailable")
    assert submit(api).status_code == 500
    with api.service._session() as session:
        task = session.scalar(select(AsyncTask))
        assert task.status == "failed"
        assert task.error_message == "failed to publish task to broker"
        assert session.get(Evaluation, api.evaluation_id).status == "pending"
    api.publisher.side_effect = None
    assert submit(api).status_code == 201


def test_submitted_task_runs_real_worker_to_completion(api, monkeypatch):
    with api.service._session() as session, session.begin():
        session.add(
            Problem(
                id=str(uuid.uuid4()),
                problem_id="p1",
                title="Add",
                description="Return the input integer plus one.",
                difficulty="easy",
                tags=[],
                test_cases=[{"input": {"x": 1}, "expected_output": 2}],
            )
        )
    response = submit(api)
    assert response.status_code == 201, response.text
    data = response.json()["data"]

    def execute(self, strategy_config, problem, strategy, sandbox):
        with api.service._session() as session:
            assert session.get(Evaluation, api.evaluation_id).status == "running"
            assert session.get(AsyncTask, data["id"]).status == "running"
        return ExecutionResult(
            problem_id="p1",
            strategy="vanilla",
            status="success",
            generated_code="def solution(x): return x + 1",
            total_tokens=10,
            execution_time_seconds=0.1,
            difficulty="easy",
        )

    monkeypatch.setattr(
        AlgorithmHarness, "_prepare_strategy_runtime", lambda *a: (object(), object())
    )
    monkeypatch.setattr(AlgorithmHarness, "_execute_problem", execute)
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", lambda *a: (0.001, {}))
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda *a, **k: None)
    monkeypatch.setattr("src.tasks.evaluation.publish_progress", lambda *a, **k: None)
    monkeypatch.setattr("src.tasks.evaluation.get_db_session", api.service._session)
    run_evaluation_task.push_request(id=data["celery_task_id"])
    try:
        result = run_evaluation_task.run(api.evaluation_id)
    finally:
        run_evaluation_task.pop_request()
    assert result["status"] == "completed", result
    assert result["completed_units"] == 1
    with api.service._session() as session:
        evaluation = session.get(Evaluation, api.evaluation_id)
        assert (evaluation.status, evaluation.completed_count) == ("completed", 1)
        assert session.get(AsyncTask, data["id"]).status == "completed"
        assert session.scalar(select(EvaluationResult)).status == "success"
