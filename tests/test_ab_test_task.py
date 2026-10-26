"""A/B queue lifecycle regressions using the real business database."""

import json
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import select

from api.db.models import ABTest, AsyncTask
from api.services.ab_test_service import ABTestService
from src.task_manager import TaskManager


@pytest.fixture
def service(tmp_path):
    service = ABTestService()
    with service._session() as db:
        db.add(ABTest(id="ab-1", user_id="owner", name="test", status="pending", config={}))
        db.commit()
    yield service
    service._engine.dispose()


def rows(service):
    with service._session() as db:
        return db.get(ABTest, "ab-1"), db.scalars(select(AsyncTask)).all()


def enqueue(service):
    with patch("src.task_manager.celery_app.send_task"):
        return service.start_test("ab-1", "owner")


def test_start_commits_before_publish_and_returns_persisted_task(service):
    def publish(name, *, args, kwargs, task_id):
        row, tasks = rows(service)
        assert name == "src.tasks.ab_test.run_ab_test_task"
        assert args == ("ab-1", "owner")
        assert kwargs == {}
        assert row.status == "pending"
        assert len(tasks) == 1
        assert tasks[0].celery_task_id == task_id
        assert tasks[0].user_id == "owner"
        assert tasks[0].task_type == "ab_test"

    with patch("src.task_manager.celery_app.send_task", side_effect=publish):
        view = service.start_test("ab-1", "owner")
    assert view["status"] == "pending"
    assert service.get_test("ab-1", "owner")["task_id"] == view["task_id"]
    with pytest.raises(ValueError):
        service.start_test("ab-1", "owner")
    with pytest.raises(ValueError):
        service.delete_test("ab-1", "owner")


def test_publish_failure_ends_both_records(service):
    with patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")):
        with pytest.raises(RuntimeError, match="broker down"):
            service.start_test("ab-1", "owner")
    row, tasks = rows(service)
    assert row.status == tasks[0].status == "failed"
    assert row.error_message == tasks[0].error_message
    assert row.completed_at is not None
    assert tasks[0].completed_at is not None


def test_concurrent_start_publishes_only_once(service):
    def start(_):
        try:
            return service.start_test("ab-1", "owner")["task_id"]
        except ValueError:
            return None

    with patch("src.task_manager.celery_app.send_task") as publish:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(start, range(2)))
    assert sum(value is not None for value in results) == 1
    assert len(rows(service)[1]) == 1
    assert publish.call_count == 1


@pytest.mark.parametrize("status", [None, "pending", "running", "paused"])
def test_restart_preserves_unstarted_and_live_tests(service, status):
    if status:
        enqueue(service)
        with service._session() as db:
            db.get(ABTest, "ab-1").status = "running" if status == "running" else "pending"
            db.scalars(select(AsyncTask)).one().status = status
            db.commit()
    before = rows(service)[0].status
    restarted = ABTestService()
    restarted._engine.dispose()
    assert rows(service)[0].status == before


def test_start_rejects_other_owner(service):
    with pytest.raises(ValueError, match="not found"):
        service.start_test("ab-1", "other")
    assert rows(service)[1] == []


def test_worker_success_and_duplicate_delivery(service, tmp_path):
    from src.tasks.ab_test import run_ab_test_task

    view = enqueue(service)
    report = tmp_path / "report"
    report.mkdir()
    (report / "ab_test.json").write_text(json.dumps({"significance": {"p_value": 0.5}}))
    runner = SimpleNamespace(run=Mock(return_value=report))
    service._runner_factory = lambda _: runner
    with (
        patch("api.services.ab_test_service.ABTestService", return_value=service),
        patch("api.auth.config.AuthSettings"),
        patch("api.auth.service.AuthService"),
        patch.object(service, "_build_config", return_value=object()),
    ):
        result = run_ab_test_task("ab-1", "owner")
        repeated = run_ab_test_task("ab-1", "owner")
    row, tasks = rows(service)
    assert result["status"] == repeated["status"] == row.status == tasks[0].status == "completed"
    assert tasks[0].id == view["task_id"]
    assert row.started_at is not None and row.completed_at is not None
    assert tasks[0].started_at is not None and tasks[0].completed_at is not None
    assert runner.run.call_count == 1
    assert service.results("ab-1", "owner")["significance"]["p_value"] == 0.5


def test_execute_failure_records_both_errors(service):
    enqueue(service)
    with patch.object(service, "_build_config", side_effect=RuntimeError("invalid config")):
        service._execute("ab-1", "owner")
    row, tasks = rows(service)
    assert row.status == tasks[0].status == "failed"
    assert row.error_message == tasks[0].error_message == "invalid config"
    assert row.completed_at is not None and tasks[0].completed_at is not None


@pytest.mark.parametrize("state", ["paused", "cancelled"])
def test_stop_during_execution_preserves_both_states(service, tmp_path, state):
    view = enqueue(service)

    def stop():
        with service._session() as db:
            with (
                patch("src.task_manager.celery_app.AsyncResult") as result,
                patch("src.task_manager.celery_app.control.revoke"),
            ):
                result.return_value.state = "PENDING"
                manager = TaskManager(db)
                if state == "paused":
                    manager.pause_task(view["task_id"], "owner")
                else:
                    manager.cancel_task(view["task_id"], "owner")
        assert runner.should_stop()
        return tmp_path

    runner = SimpleNamespace(run=stop)
    service._runner_factory = lambda _: runner
    with patch.object(service, "_build_config", return_value=object()):
        service._execute("ab-1", "owner")
    row, tasks = rows(service)
    assert row.status == tasks[0].status == state
    assert row.output_dir is None


@pytest.mark.parametrize("state", ["FAILURE", "REVOKED"])
def test_broker_terminal_state_syncs_business_record(service, state):
    view = enqueue(service)
    with service._session() as db, patch("src.task_manager.celery_app.AsyncResult") as result:
        result.return_value.state = state
        result.return_value.info = "worker lost"
        TaskManager(db).get_task(view["task_id"], "owner")
    row, tasks = rows(service)
    assert row.status == tasks[0].status == ("failed" if state == "FAILURE" else "cancelled")
    assert row.completed_at is not None


@pytest.mark.parametrize("state", ["paused", "cancelled", "completed", "failed", "running"])
def test_duplicate_message_never_restarts_existing_task(service, state):
    enqueue(service)
    with service._session() as db:
        task = db.scalars(select(AsyncTask)).one()
        task.status = state
        db.get(ABTest, "ab-1").status = state
        db.commit()
    with patch.object(service, "_build_config") as build:
        result = service._execute("ab-1", "owner")
    assert result["status"] == state
    assert build.call_count == 0
    assert rows(service)[0].status == state


def test_stale_message_id_is_rejected(service):
    enqueue(service)
    with pytest.raises(ValueError, match="not found"):
        service._execute("ab-1", "owner", celery_task_id="stale-message")
    assert rows(service)[0].status == "pending"


def test_broker_started_event_does_not_preempt_atomic_claim(service):
    view = enqueue(service)
    with service._session() as db, patch("src.task_manager.celery_app.AsyncResult") as result:
        result.return_value.state = "STARTED"
        TaskManager(db).get_task(view["task_id"], "owner")
    assert rows(service)[1][0].status == "pending"


def test_worker_rejects_other_owner_without_changing_records(service):
    enqueue(service)
    with pytest.raises(ValueError, match="not found"):
        service._execute("ab-1", "other")
    assert rows(service)[0].status == rows(service)[1][0].status == "pending"
