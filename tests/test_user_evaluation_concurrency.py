"""Shared-database evaluation admission: removing the gate must over-admit."""

import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select

from api.auth.dependencies import auth_service, current_user
from api.config import Settings, settings
from api.db import make_engine, make_session_factory, run_migrations
from api.db.models import AsyncTask, Evaluation
from api.middleware.errors import setup_error_handlers
from api.models import EvaluationCreateRequest
from api.routes.evaluations import call, evaluation_service, router
from api.services.evaluation_service import EvaluationService
from src.task_manager import TaskManager, celery_app


@pytest.fixture
def environment(tmp_path, monkeypatch):
    monkeypatch.setitem(settings.__dict__, "MAX_CONCURRENT_EVALUATIONS_PER_USER", 1)
    engine = make_engine(f"sqlite:///{tmp_path / 'admission.sqlite3'}")
    run_migrations(engine)
    factory = make_session_factory(engine)
    publisher = Mock(side_effect=lambda *a, **kw: SimpleNamespace(id=str(uuid.uuid4())))
    monkeypatch.setattr(celery_app, "send_task", publisher)
    monkeypatch.setattr(celery_app, "AsyncResult", lambda _: SimpleNamespace(state="PENDING"))
    yield engine, factory, publisher
    engine.dispose()


def submit(session, owner="alice", method="enqueue_task", task_type="evaluation"):
    return getattr(TaskManager(session), method)(
        task_type=task_type,
        entity_id=str(uuid.uuid4()),
        user_id=owner,
        celery_task_name="src.tasks.evaluation.run_evaluation_task",
    )


@pytest.mark.parametrize("method", ["enqueue_task", "create_task"])
def test_full_user_rejected_without_candidate_or_publication(environment, method):
    _, factory, publisher = environment
    with factory() as first:
        submit(first, method=method)
    with factory() as second:
        with pytest.raises(ValueError, match="concurren"):
            submit(second, method=method)
        second.rollback()
    with factory() as reader:
        assert reader.scalar(select(func.count()).select_from(AsyncTask)) == 1
    assert publisher.call_count == 1


@pytest.mark.parametrize(
    "status,blocked",
    [
        ("pending", True),
        ("running", True),
        ("paused", False),
        ("completed", False),
        ("failed", False),
        ("cancelled", False),
    ],
)
def test_status_controls_admission(environment, status, blocked):
    _, factory, _ = environment
    with factory() as session:
        old = submit(session)
        old.status = status
        session.commit()
    with factory() as session:
        if blocked:
            with pytest.raises(ValueError, match="concurren"):
                submit(session)
        else:
            assert submit(session).status == "pending"


def test_users_and_other_task_types_have_independent_capacity(environment):
    _, factory, publisher = environment
    with factory() as session:
        submit(session, task_type="import")
        submit(session)
        assert submit(session, owner="bob").status == "pending"
        assert submit(session, task_type="experiment").status == "pending"
    assert publisher.call_count == 4


@pytest.mark.parametrize("method", ["enqueue_task", "create_task"])
def test_publish_failure_releases_capacity(environment, method):
    _, factory, publisher = environment
    publisher.side_effect = ConnectionError("broker down")
    with factory() as session:
        with pytest.raises(ConnectionError):
            submit(session, method=method)
        session.rollback()
    publisher.side_effect = lambda *a, **kw: SimpleNamespace(id=str(uuid.uuid4()))
    with factory() as session:
        assert submit(session, method=method).status == "pending"


def test_link_failure_rolls_back_capacity(environment):
    _, factory, publisher = environment

    def reject(_task):
        raise ValueError("link rejected")

    with factory() as session:
        with pytest.raises(ValueError, match="link rejected"):
            TaskManager(session).enqueue_task(
                "evaluation", "entity", "alice", "worker", on_before_publish=reject
            )
        session.rollback()
    with factory() as session:
        assert submit(session).status == "pending"
    assert publisher.call_count == 1


@pytest.mark.parametrize("limit", [0, -1])
def test_configuration_rejects_nonpositive_capacity(limit):
    with pytest.raises(ValidationError):
        Settings(MAX_CONCURRENT_EVALUATIONS_PER_USER=limit, _env_file=None)


def request():
    return EvaluationCreateRequest(
        api_key_id="credential", problem_ids=["p1"], strategy_names=["vanilla"], model="test"
    )


def test_service_start_async_create_and_resume_use_gate(environment):
    engine, factory, publisher = environment
    service = EvaluationService(str(engine.url))
    try:
        draft = service.create_evaluation(request(), "alice")
        other = service.create_evaluation_async(request(), "alice")
        with pytest.raises(HTTPException) as error:
            call(lambda: service.start_evaluation(draft.evaluation_id, "alice"))
        assert error.value.status_code == 429
        with pytest.raises(ValueError, match="concurren"):
            service.create_evaluation_async(request(), "alice")
        with factory() as session:
            evaluation = session.get(Evaluation, other.evaluation_id)
            session.get(AsyncTask, evaluation.async_task_id).status = "paused"
            session.commit()
        service.start_evaluation(draft.evaluation_id, "alice")
        with pytest.raises(ValueError, match="concurren"):
            service.resume_evaluation(other.evaluation_id, "alice")
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(Evaluation)) == 2
            assert session.scalar(select(func.count()).select_from(AsyncTask)) == 2
        assert publisher.call_count == 2
    finally:
        service.close()


def test_http_start_reports_quota_and_preserves_draft(environment):
    engine, factory, publisher = environment
    service = EvaluationService(str(engine.url))
    app = setup_error_handlers(FastAPI())
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(user_id="alice")
    app.dependency_overrides[auth_service] = lambda: SimpleNamespace(
        owned_key=lambda *_: None, audit=lambda *_: None
    )
    app.dependency_overrides[evaluation_service] = lambda: service
    try:
        first = service.create_evaluation(request(), "alice")
        second = service.create_evaluation(request(), "alice")
        with TestClient(app) as client:
            assert (
                client.post(f"/api/v1/evaluations/{first.evaluation_id}/start").status_code == 202
            )
            rejected = client.post(f"/api/v1/evaluations/{second.evaluation_id}/start")
            assert rejected.status_code == 429
            assert rejected.json()["error"]["code"] == "QUOTA_EXCEEDED"
            assert client.get(f"/api/v1/evaluations/{second.evaluation_id}").json()["data"][
                "can_start"
            ]
        with factory() as session:
            assert session.get(Evaluation, second.evaluation_id).async_task_id is None
        assert publisher.call_count == 1
    finally:
        service.close()


def test_postgresql_advisory_lock_is_bound_stable_and_precedes_count(environment):
    # No local PG server: exercise the branch through a real Session/connection
    # and intercept only the server-specific statement, retaining the real count.
    from sqlalchemy import event

    engine, factory, _ = environment
    statements = []
    keys = []

    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement)
        if "pg_advisory_xact_lock" in statement:
            keys.append(parameters[0])
            return "SELECT 1", ()
        return statement, parameters

    event.listen(engine, "before_cursor_execute", capture, retval=True)
    try:
        # Change only dialect identity for selecting the gate branch; SQLite's
        # actual SQL compiler and parameter binding remain in use.
        original_name = engine.dialect.name
        engine.dialect.name = "postgresql"
        for owner in ("alice", "alice", "bob"):
            with factory() as session:
                TaskManager(session)._check_evaluation_capacity("evaluation", owner)
                session.rollback()
    finally:
        engine.dialect.name = original_name
        event.remove(engine, "before_cursor_execute", capture)
    assert len(keys) == 3
    assert keys[0] == keys[1] and keys[0] != keys[2]
    assert -(2**63) <= keys[0] < 2**63
    assert "pg_advisory_xact_lock" in statements[0]
    assert "count(" in statements[1].lower()


def test_independent_processes_share_one_remaining_slot(environment, tmp_path):
    engine, factory, _ = environment
    # Each child imports the real manager, owns its engine and waits for the
    # same release file. Slow the count-to-insert window to expose a missing lock.
    script = """
import json, pathlib, sys, time, uuid
from types import SimpleNamespace
from sqlalchemy import event
from api.db import make_engine, make_session_factory
from src.task_manager import TaskManager, celery_app
engine = make_engine(sys.argv[1])
@event.listens_for(engine, "after_cursor_execute")
def delay(conn, cursor, statement, parameters, context, many):
    if statement.lstrip().upper().startswith("SELECT") and "count(" in statement.lower():
        time.sleep(0.15)
celery_app.send_task = lambda *a, **kw: SimpleNamespace(id=str(uuid.uuid4()))
pathlib.Path(sys.argv[2]).touch()
while not pathlib.Path(sys.argv[3]).exists():
    time.sleep(0.01)
with make_session_factory(engine)() as session:
    try:
        TaskManager(session).enqueue_task("evaluation", str(uuid.uuid4()), "alice", "worker")
        print(json.dumps({"accepted": True}))
    except ValueError:
        session.rollback()
        print(json.dumps({"accepted": False}))
engine.dispose()
"""
    import time

    release = tmp_path / "release"
    children = []
    env = {**os.environ, "MAX_CONCURRENT_EVALUATIONS_PER_USER": "1"}
    try:
        for index in range(4):
            ready = tmp_path / f"ready-{index}"
            child = subprocess.Popen(
                [sys.executable, "-c", script, str(engine.url), str(ready), str(release)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            children.append(child)
        deadline = time.monotonic() + 30
        while len(list(tmp_path.glob("ready-*"))) != 4:
            assert time.monotonic() < deadline, "children did not reach admission barrier"
            time.sleep(0.01)
        release.touch()
        results = []
        for child in children:
            stdout, stderr = child.communicate(timeout=30)
            assert child.returncode == 0, stderr
            results.append(json.loads(stdout)["accepted"])
        assert results.count(True) == 1
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(AsyncTask)) == 1
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait()
