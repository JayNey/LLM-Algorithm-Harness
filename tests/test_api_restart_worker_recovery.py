"""API startup must not interrupt tasks owned by an independent worker."""

import json
from contextlib import ExitStack
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from api.auth.config import AuthSettings
from api.db.models import AsyncTask, BenchmarkRun, BenchmarkSuite, Evaluation, Experiment
from api.experiment_models import ExperimentCreateRequest
from api.files.config import FileSettings
from api.main import create_app
from api.models import EvaluationCreateRequest
from api.services.benchmark_service import BenchmarkService
from api.services.evaluation_service import EvaluationService
from api.services.experiment_service import ExperimentService
from src.tasks.experiment import run_experiment_task

SERVICE_TYPES = {
    "evaluation": (EvaluationService, Evaluation),
    "experiment": (ExperimentService, Experiment),
    "benchmark": (BenchmarkService, BenchmarkRun),
}
STAMP = datetime(2026, 10, 21, 12, 0, 0)
PROGRESS = {"current": 1, "total": 2, "percentage": 50.0, "current_step": "vanilla/p1"}


def seed(session, kind, status, task_status, *, owner_id="owner-1", error_message=None):
    """Persist a business record and optional independently managed task."""
    if kind == "benchmark":
        session.add(BenchmarkSuite(id="suite-1", user_id=owner_id, name="suite"))
        session.flush()
    task = None
    if task_status is not None:
        task = AsyncTask(
            id="task-1",
            celery_task_id="celery-1",
            task_type=kind,
            entity_id="entity-1",
            user_id=owner_id,
            status=task_status,
            progress=PROGRESS,
            updated_at=STAMP,
        )
        session.add(task)
        session.flush()
    extra = {}
    if kind == "evaluation":
        extra["async_task_id"] = task.id if task else None
    elif kind == "benchmark":
        extra["suite_id"] = "suite-1"
    model = SERVICE_TYPES[kind][1]
    row = model(
        id="entity-1",
        user_id=owner_id,
        status=status,
        updated_at=STAMP,
        error_message=error_message,
        **extra,
    )
    session.add(row)
    session.commit()
    return row


@pytest.fixture(params=SERVICE_TYPES)
def service(request, tmp_path):
    kind = request.param
    service_cls, model = SERVICE_TYPES[kind]
    url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
    original = service_cls(url)
    yield kind, model, original, url
    original._engine.dispose()


@pytest.mark.parametrize("status", ["pending", "running"])
@pytest.mark.parametrize(
    "task_status", [None, "pending", "running", "paused", "completed", "failed", "cancelled"]
)
def test_restart_preserves_records_with_live_worker_tasks(service, status, task_status):
    kind, model, original, url = service
    with original._session() as session:
        seed(session, kind, status, task_status)

    restarted = type(original)(url)
    try:
        with restarted._session() as session:
            row = session.get(model, "entity-1")
            if task_status in ("pending", "running", "paused") or (
                kind != "benchmark" and status == "pending" and task_status is None
            ):
                assert row.status == status
                assert row.error_message is None
                assert row.updated_at == STAMP
            else:
                assert row.status == "failed"
                assert row.error_message == "interrupted by service restart"
            if kind == "evaluation":
                assert row.async_task_id == ("task-1" if task_status else None)
            if task_status is not None:
                task = session.get(AsyncTask, "task-1")
                assert task.status == task_status
                assert task.progress == PROGRESS
                assert task.updated_at == STAMP
    finally:
        restarted._engine.dispose()


@pytest.mark.parametrize("status", ["paused", "completed", "failed", "cancelled"])
def test_restart_preserves_terminal_and_paused_records(service, status):
    kind, model, original, url = service
    with original._session() as session:
        seed(session, kind, status, "running", error_message="existing diagnostic")

    restarted = type(original)(url)
    try:
        with restarted._session() as session:
            row = session.get(model, "entity-1")
            assert row.status == status
            assert row.error_message == "existing diagnostic"
            assert row.updated_at == STAMP
    finally:
        restarted._engine.dispose()


def test_experiment_worker_completes_and_links_results_after_api_restart(tmp_path):
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY="test-secret-" * 5,
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )
    files = FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads")
    url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
    original = create_app(auth, files, database_url=url)
    with TestClient(original) as client:
        registered = client.post(
            "/api/v1/auth/register",
            json={
                "username": "alice",
                "email": "alice@example.org",
                "password": "test-password-long-!",
            },
        )
        assert registered.status_code == 201
        owner_id = registered.json()["data"]["id"]
        login = client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": "test-password-long-!"}
        )
        headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
        with original.state.task_session_factory() as session:
            seed(session, "experiment", "pending", "pending", owner_id=owner_id)

    output_dir = tmp_path / "experiment-artifacts"
    output_dir.mkdir()
    (output_dir / "experiment.json").write_text(
        json.dumps({"experiment_id": "entity-1", "name": "restart regression", "combinations": []}),
        encoding="utf-8",
    )
    revived = create_app(auth, files, database_url=url)
    clients = []
    with ExitStack() as stack:

        class Runner:
            def run(self):
                # The independent worker is still inside runner.run when API startup runs.
                clients.append(stack.enter_context(TestClient(revived)))
                return output_dir

        worker = ExperimentService(url, runner_factory=lambda _config: Runner(), recover=False)
        try:
            with (
                patch("src.tasks.experiment.get_db_session", worker._session),
                patch("src.tasks.experiment.execute_experiment", worker._execute),
                patch.object(worker, "_build_runner_config", return_value=SimpleNamespace()),
            ):
                result = run_experiment_task.run("entity-1", owner_id)
            assert result == {"experiment_id": "entity-1", "status": "completed"}
            with revived.state.task_session_factory() as session:
                experiment = session.get(Experiment, "entity-1")
                assert experiment.status == "completed"
                assert experiment.output_dir == str(output_dir)
                assert experiment.completed_at is not None
                assert experiment.error_message is None
                assert session.get(AsyncTask, "task-1").status == "completed"
            response = clients[0].get("/api/v1/experiments/entity-1/results", headers=headers)
            assert response.status_code == 200, response.text
            assert response.json()["data"]["experiment_id"] == "entity-1"
        finally:
            worker._engine.dispose()


@pytest.fixture(params=["evaluation", "experiment"])
def draft(request, tmp_path):
    kind = request.param
    cls, model = SERVICE_TYPES[kind]
    url = f"sqlite:///{tmp_path / 'draft.sqlite3'}"
    original = cls(url)
    if kind == "evaluation":
        row = original.create_evaluation(
            EvaluationCreateRequest(
                api_key_id="key", model="test", problem_ids=["p1"], strategy_names=["vanilla"]
            ),
            "owner-1",
        )
        entity_id = row.evaluation_id
    else:
        original._auth = Mock()
        with patch("api.services.experiment_service.freeze_dataset", return_value={}):
            row = original.create_experiment(
                ExperimentCreateRequest(
                    name="draft",
                    dataset_id="dataset",
                    api_key_id="key",
                    models=[{"model": "test"}],
                    strategies=[{"name": "vanilla"}],
                ),
                "owner-1",
            )
        entity_id = row["id"]
    yield kind, model, original, url, entity_id
    original._engine.dispose()


def start(service, kind, entity_id):
    return getattr(service, f"start_{kind}")(entity_id, "owner-1")


@pytest.mark.parametrize("close_original", [False, True])
def test_unstarted_draft_survives_rebuild_and_starts_once(draft, close_original):
    kind, model, original, url, entity_id = draft
    with original._session() as db:
        before = {
            c.name: getattr(db.get(model, entity_id), c.name) for c in model.__table__.columns
        }
    if close_original:
        original._engine.dispose()
    restarted = type(original)(url)
    try:
        restarted._recover_interrupted()
        with restarted._session() as db:
            row = db.get(model, entity_id)
            assert {c.name: getattr(row, c.name) for c in model.__table__.columns} == before
        with patch("src.task_manager.celery_app.send_task") as publish:
            start(restarted, kind, entity_id)
            restarted._recover_interrupted()
            with pytest.raises(ValueError, match="already queued"):
                start(restarted, kind, entity_id)
        assert publish.call_count == 1
        with restarted._session() as db:
            tasks = list(db.scalars(select(AsyncTask).where(AsyncTask.entity_id == entity_id)))
            assert len(tasks) == 1
            assert tasks[0].status == "pending"
            assert db.get(model, entity_id).status == "pending"
    finally:
        restarted._engine.dispose()


@pytest.mark.parametrize("evidence", ["started", "history", "unlinked-history"])
def test_pending_with_execution_evidence_is_not_a_draft(draft, evidence):
    kind, model, service, url, entity_id = draft
    with service._session() as db, db.begin():
        row = db.get(model, entity_id)
        if evidence == "started":
            row.started_at = STAMP
        else:
            task = AsyncTask(
                id="past",
                celery_task_id="past",
                task_type=kind,
                entity_id=entity_id,
                user_id="owner-1",
                status="failed",
            )
            db.add(task)
            db.flush()
            if kind == "evaluation" and evidence == "history":
                row.async_task_id = task.id
    service._recover_interrupted()
    with service._session() as db:
        row = db.get(model, entity_id)
        assert row.status == "failed"
        assert row.error_message == "interrupted by service restart"
        updated = row.updated_at
    service._recover_interrupted()
    with service._session() as db:
        assert db.get(model, entity_id).updated_at == updated


@pytest.mark.parametrize("operation", ["start", "complete", "create"])
def test_recovery_does_not_overwrite_concurrent_lifecycle_change(draft, operation):
    kind, model, service, url, entity_id = draft
    # Complete begins with a genuine orphan; start/create begin with an unstarted draft.
    if operation == "complete":
        with service._session() as db, db.begin():
            db.get(model, entity_id).status = "running"
    changed = False

    def before_update(_conn, _cursor, statement, *_args):
        nonlocal changed
        if changed or not statement.startswith(f"UPDATE {model.__tablename__}"):
            return
        changed = True
        if operation == "start":
            start(service, kind, entity_id)
        else:
            with service._session() as db, db.begin():
                if operation == "complete":
                    row = db.get(model, entity_id)
                    row.status = "completed"
                    row.completed_at = STAMP
                else:
                    db.add(model(id="new-draft", user_id="owner-1", status="pending"))

    event.listen(service._engine, "before_cursor_execute", before_update)
    try:
        with patch("src.task_manager.celery_app.send_task"):
            service._recover_interrupted()
    finally:
        event.remove(service._engine, "before_cursor_execute", before_update)
    assert changed
    with service._session() as db:
        row = db.get(model, entity_id)
        assert row.status == ("completed" if operation == "complete" else "pending")
        assert row.error_message is None
        if operation == "start":
            assert len(list(db.scalars(select(AsyncTask)))) == 1
        elif operation == "complete":
            assert row.completed_at == STAMP
        else:
            assert db.get(model, "new-draft").status == "pending"


@pytest.mark.parametrize("task_status", ["pending", "running", "paused"])
def test_recovery_preserves_owned_live_task_even_without_evaluation_link(draft, task_status):
    kind, model, service, url, entity_id = draft
    with service._session() as db, db.begin():
        db.add(
            AsyncTask(
                id="live",
                celery_task_id="live",
                task_type=kind,
                entity_id=entity_id,
                user_id="owner-1",
                status=task_status,
            )
        )
    service._recover_interrupted()
    with service._session() as db:
        assert db.get(model, entity_id).status == "pending"
        assert db.get(AsyncTask, "live").status == task_status


@pytest.mark.parametrize("task_status", ["pending", "failed"])
@pytest.mark.parametrize("wrong", ["owner", "type"])
def test_unrelated_task_does_not_count_as_draft_execution_history(draft, task_status, wrong):
    kind, model, service, url, entity_id = draft
    with service._session() as db, db.begin():
        db.add(
            AsyncTask(
                id="unrelated",
                celery_task_id="unrelated",
                task_type=kind if wrong == "owner" else "import",
                entity_id=entity_id,
                user_id="other" if wrong == "owner" else "owner-1",
                status=task_status,
            )
        )
    service._recover_interrupted()
    with service._session() as db:
        assert db.get(model, entity_id).status == "pending"
        # A foreign live task must not protect a genuine orphan either.
        db.get(model, entity_id).status = "running"
        db.commit()
    service._recover_interrupted()
    with service._session() as db:
        assert db.get(model, entity_id).status == "failed"
        assert db.get(AsyncTask, "unrelated").status == task_status
