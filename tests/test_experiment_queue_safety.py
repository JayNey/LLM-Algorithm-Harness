"""One queued execution per experiment, including independent API processes (#296)."""

import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

import pytest
from sqlalchemy import event, select

from api.db.models import AsyncTask, Experiment
from api.services.experiment_service import ExperimentService
from src.task_manager import TaskManager


@pytest.fixture
def service(tmp_path):
    service = ExperimentService(f"sqlite:///{tmp_path}/queue.db", recover=False)
    with service._session() as db:
        db.add(Experiment(id="exp", user_id="owner", status="pending"))
        db.commit()
    yield service
    service._engine.dispose()


def tasks(service):
    with service._session() as db:
        return list(db.scalars(select(AsyncTask)))


def test_sequential_submit_once_and_restore_association(service):
    assert service.get_experiment("exp", "owner").get("task_id") is None
    with patch("src.task_manager.celery_app.send_task") as publish:
        first = service.start_experiment("exp", "owner")
        with pytest.raises(ValueError, match="already queued"):
            service.start_experiment("exp", "owner")
    assert publish.call_count == 1
    assert len(tasks(service)) == 1
    assert first["status"] == "pending"
    assert service.get_experiment("exp", "owner")["task_id"] == first["task_id"]
    rows, total = service.list_experiments("owner")
    assert total == 1 and rows[0]["task_id"] == first["task_id"]


def _process_submit(url, ready, start, result):
    service = ExperimentService(url, recover=False)
    try:
        with patch("src.task_manager.celery_app.send_task") as publish:
            ready.put(True)
            if not start.wait(30):
                raise TimeoutError("submission gate")
            try:
                outcome = service.start_experiment("exp", "owner")["task_id"]
            except ValueError as exc:
                outcome = str(exc)
            result.put((outcome, publish.call_count))
    finally:
        service._engine.dispose()


def test_independent_processes_publish_only_one_task(service):
    ctx = multiprocessing.get_context("spawn")
    ready, result, start = ctx.Queue(), ctx.Queue(), ctx.Event()
    processes = [
        ctx.Process(
            target=_process_submit,
            args=(str(service._engine.url), ready, start, result),
        )
        for _ in range(3)
    ]
    try:
        for process in processes:
            process.start()
        for _ in processes:
            assert ready.get(timeout=30)
        start.set()
        outcomes = [result.get(timeout=30) for _ in processes]
        for process in processes:
            process.join(10)
            assert process.exitcode == 0
        assert sum(count for _, count in outcomes) == 1
        assert sum("already queued" in outcome for outcome, _ in outcomes) == 2
        assert len(tasks(service)) == 1
    finally:
        start.set()
        for process in processes:
            if process.is_alive():
                process.terminate()
            process.join(10)
        ready.close()
        result.close()


@pytest.mark.parametrize("status", ["pending", "running", "paused"])
def test_active_task_blocks_delete_even_if_business_is_pending(service, status):
    with patch("src.task_manager.celery_app.send_task"):
        task_id = service.start_experiment("exp", "owner")["task_id"]
    with service._session() as db:
        db.get(AsyncTask, task_id).status = status
        db.commit()
    with pytest.raises(ValueError, match="Cannot delete"):
        service.delete_experiment("exp", "owner")
    assert service.get_experiment("exp", "owner")["status"] == "pending"


@pytest.mark.parametrize("first", ["start", "delete"])
def test_start_and_delete_are_serialized(service, first):
    entered, release = Event(), Event()

    def hold_write(_conn, _cursor, statement, *_):
        if not entered.is_set() and (
            statement.startswith("UPDATE experiments")
            or statement.startswith("INSERT INTO async_tasks")
            or statement.startswith("DELETE FROM experiments")
        ):
            entered.set()
            assert release.wait(10)

    def run(operation):
        try:
            if operation == "start":
                return service.start_experiment("exp", "owner")
            return service.delete_experiment("exp", "owner")
        except ValueError as exc:
            return str(exc)

    event.listen(service._engine, "after_cursor_execute", hold_write)
    with patch("src.task_manager.celery_app.send_task") as publish:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(run, first)
            try:
                assert entered.wait(10)
                b = pool.submit(run, "delete" if first == "start" else "start")
            finally:
                release.set()
            assert not isinstance(a.result(10), str)
            outcome = b.result(10)
        event.remove(service._engine, "after_cursor_execute", hold_write)
    if first == "start":
        assert isinstance(outcome, str) and "Cannot delete" in outcome
        assert publish.call_count == 1 and len(tasks(service)) == 1
        assert service.get_experiment("exp", "owner")["status"] == "pending"
    else:
        assert isinstance(outcome, str) and "not found" in outcome
        assert publish.call_count == 0 and tasks(service) == []


def test_publish_failure_is_terminal_and_deletable(service):
    with patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")):
        with pytest.raises(RuntimeError, match="broker down"):
            service.start_experiment("exp", "owner")
    task = tasks(service)[0]
    view = service.get_experiment("exp", "owner")
    assert task.status == view["status"] == "failed"
    assert "publish" in view["error_message"]
    assert view["task_id"] == task.id
    assert task.completed_at is not None
    with pytest.raises(ValueError, match="Cannot start"):
        service.start_experiment("exp", "owner")
    service.delete_experiment("exp", "owner")


@pytest.mark.parametrize("status", ["running", "cancelled"])
def test_publish_timeout_preserves_concurrent_transition(service, status):
    def delivered(*_, **__):
        with service._session() as db:
            task = db.scalar(select(AsyncTask))
            TaskManager(db).update_task_status(task.id, status)
        raise RuntimeError("publish timed out after delivery")

    with patch("src.task_manager.celery_app.send_task", side_effect=delivered):
        with pytest.raises(RuntimeError, match="timed out"):
            service.start_experiment("exp", "owner")
    assert tasks(service)[0].status == service.get_experiment("exp", "owner")["status"] == status


def test_owner_and_task_type_isolation(service):
    with service._session() as db:
        for id_, type_, owner in [
            ("foreign", "experiment", "other"),
            ("wrong-type", "ab_test", "owner"),
        ]:
            db.add(
                AsyncTask(
                    id=id_,
                    celery_task_id=id_,
                    task_type=type_,
                    entity_id="exp",
                    user_id=owner,
                    status="pending",
                )
            )
        db.commit()
    assert service.get_experiment("exp", "owner").get("task_id") is None
    with patch("src.task_manager.celery_app.send_task") as publish:
        for operation in [
            service.start_experiment,
            service.delete_experiment,
            service.get_experiment,
        ]:
            with pytest.raises(ValueError, match="not found"):
                operation("exp", "other")
        assert service.list_experiments("other") == ([], 0)
        publish.assert_not_called()
        own = service.start_experiment("exp", "owner")
    assert own["task_id"] not in ("foreign", "wrong-type")
    assert service.get_experiment("exp", "owner")["task_id"] == own["task_id"]
