"""Cancellation must win over stale experiment workers and status readers (#295)."""

from datetime import datetime
from threading import Event, Thread, current_thread
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import event

from api.db.models import AsyncTask, Experiment
from api.services.experiment_service import ExperimentService
from src.task_manager import TaskManager
from src.tasks.experiment import run_experiment_task

START = datetime(2026, 10, 28, 1, 0)


@pytest.fixture
def service(tmp_path):
    service = ExperimentService(f"sqlite:///{tmp_path}/experiment.db", recover=False)
    with service._session() as db:
        db.add(Experiment(id="exp", user_id="owner", status="running", started_at=START))
        db.add(
            AsyncTask(
                id="task",
                celery_task_id="celery",
                task_type="experiment",
                entity_id="exp",
                user_id="owner",
                status="running",
                started_at=START,
                progress={"current": 1, "total": 3, "percentage": 100 / 3},
            )
        )
        db.commit()
    with (
        patch("src.task_manager.celery_app.control.revoke"),
        patch(
            "src.task_manager.celery_app.AsyncResult", return_value=SimpleNamespace(state="PENDING")
        ),
    ):
        yield service
    service._engine.dispose()


def cancel(service):
    with service._session() as db:
        return TaskManager(db).cancel_task("task", "owner").completed_at


def assert_cancelled(service, completed_at):
    with service._session() as db:
        task, experiment = db.get(AsyncTask, "task"), db.get(Experiment, "exp")
        assert task.status == experiment.status == "cancelled"
        assert task.started_at == experiment.started_at == START
        assert task.completed_at == experiment.completed_at == completed_at
        assert task.error_message is None and experiment.error_message is None
        assert experiment.output_dir is None
        assert task.progress["current"] == 1


@pytest.mark.parametrize("status", ["pending", "running", "paused"])
def test_cancel_synchronizes_experiment_and_allows_delete(service, status):
    with service._session() as db:
        db.get(AsyncTask, "task").status = status
        db.get(Experiment, "exp").status = status
        db.commit()
    ended = cancel(service)
    assert ended is not None
    assert_cancelled(service, ended)
    assert cancel(service) == ended
    assert service.get_experiment("exp", "owner")["status"] == "cancelled"
    service.delete_experiment("exp", "owner")
    with service._session() as db:
        assert db.get(Experiment, "exp") is None


@pytest.mark.parametrize("operation", ["running", "completed", "failed", "progress"])
def test_stale_task_writer_cannot_override_cancellation(service, operation):
    with service._session() as stale:
        task = stale.get(AsyncTask, "task")
        assert task.status == "running"
        ended = cancel(service)
        manager = TaskManager(stale)
        if operation == "progress":
            manager.update_task_progress("task", {"current": 3}, "running")
        else:
            manager.update_task_status("task", operation, error_message="late error")
    assert_cancelled(service, ended)


@pytest.mark.parametrize("state", ["STARTED", "PROGRESS", "FAILURE", "REVOKED"])
def test_celery_result_read_racing_cancel_preserves_cancelled(service, state):
    ended = []

    class Result:
        info = {"current": 3}

        @property
        def state(self):
            ended.append(cancel(service))
            return state

    with service._session() as db:
        task = db.get(AsyncTask, "task")
        with patch("src.task_manager.celery_app.AsyncResult", return_value=Result()):
            # cancel() must not recurse through Celery synchronization.
            with patch.object(
                TaskManager, "get_task", lambda self, *_: self.db.get(AsyncTask, "task")
            ):
                TaskManager(db)._sync_celery_state(task)
    assert_cancelled(service, ended[0])


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_stale_cancel_rejects_already_finished_task(service, status):
    with service._session() as stale:
        task = stale.get(AsyncTask, "task")
        assert task.status == "running"
        with service._session() as worker:
            TaskManager(worker).update_task_status("task", status)
        with pytest.raises(ValueError, match="Cannot cancel"):
            TaskManager(stale).cancel_task("task", "owner")
    with service._session() as db:
        assert db.get(AsyncTask, "task").status == status
        assert db.get(Experiment, "exp").status == status


def test_cancel_cannot_touch_another_owners_records(service):
    with service._session() as db:
        with pytest.raises(ValueError, match="not found or access denied"):
            TaskManager(db).cancel_task("task", "intruder")
        assert db.get(AsyncTask, "task").status == "running"
        experiment = db.get(Experiment, "exp")
        experiment.user_id = "someone-else"
        db.commit()
        TaskManager(db).cancel_task("task", "owner")
    with service._session() as db:
        assert db.get(Experiment, "exp").status == "running"


@pytest.mark.parametrize("status", ["completed", "failed"])
def test_cancel_respects_business_terminal_before_task_callback(service, status):
    with service._session() as db:
        row = db.get(Experiment, "exp")
        row.status = status
        row.completed_at = START
        db.commit()
    with service._session() as db:
        with pytest.raises(ValueError, match="Cannot cancel"):
            TaskManager(db).cancel_task("task", "owner")
    with service._session() as db:
        assert db.get(Experiment, "exp").status == status
        assert db.get(Experiment, "exp").completed_at == START


@pytest.mark.parametrize("deleted", [False, True])
def test_cancelled_delivery_does_not_start_or_fail(service, deleted):
    ended = cancel(service)
    if deleted:
        # Exercise deletion even before the synchronization fix permits it.
        with service._session() as db:
            db.delete(db.get(Experiment, "exp"))
            db.commit()
    with (
        patch("src.tasks.experiment.get_db_session", side_effect=service._session),
        patch(
            "src.tasks.experiment.execute_experiment",
            side_effect=AssertionError("must not execute"),
        ),
    ):
        result = run_experiment_task("exp", "owner")
    assert result["status"] == "cancelled"
    with service._session() as db:
        assert db.get(AsyncTask, "task").status == "cancelled"
        assert db.get(AsyncTask, "task").completed_at == ended


@pytest.mark.parametrize("raises", [False, True])
@pytest.mark.parametrize("deleted", [False, True])
def test_worker_late_return_or_exception_preserves_cancelled(service, raises, deleted):
    with service._session() as db:
        db.get(AsyncTask, "task").status = "pending"
        db.get(Experiment, "exp").status = "pending"
        db.commit()
    ended = []

    def execute(*_):
        ended.append(cancel(service))
        if deleted:
            with service._session() as db:
                db.delete(db.get(Experiment, "exp"))
                db.commit()
        if raises:
            raise RuntimeError("late worker error")

    with (
        patch("src.tasks.experiment.get_db_session", side_effect=service._session),
        patch("src.tasks.experiment.execute_experiment", side_effect=execute),
    ):
        result = run_experiment_task("exp", "owner")
    assert result["status"] == "cancelled"
    if not deleted:
        assert_cancelled(service, ended[0])
    else:
        with service._session() as db:
            assert db.get(AsyncTask, "task").status == "cancelled"
            assert db.get(Experiment, "exp") is None


@pytest.mark.parametrize("outcome", ["success", "failure", "stopped"])
def test_service_late_runner_outcome_preserves_cancelled(service, tmp_path, outcome):
    ended = []

    class Runner:
        paused = False

        def run(self):
            ended.append(cancel(service))
            if outcome == "failure":
                raise RuntimeError("late provider error")
            if outcome == "stopped":
                self.paused = self.should_pause()
                assert self.paused, "cancellation must stop the next combination"
            return tmp_path

    runner = Runner()
    service._runner_factory = lambda _: runner
    with patch.object(service, "_build_runner_config", return_value=object()):
        service._execute("exp", "owner")
    assert_cancelled(service, ended[0])
    if outcome == "stopped":
        assert runner.paused, "the service must request a stop at the combination boundary"


@pytest.mark.parametrize("winner", ["cancelled", "completed"])
def test_concurrent_cancel_and_completion_commit_consistent_pair(service, tmp_path, winner):
    """Block the first writer inside its transaction while the second arrives."""
    entered, release, competing = Event(), Event(), Event()
    errors = []

    def hold_first_writer(_conn, _cursor, statement, _params, _context, _many):
        name = current_thread().name
        if name == "first" and statement.startswith("UPDATE experiments") and not entered.is_set():
            entered.set()
            assert release.wait(10), "test did not release the first transaction"
        if name == "second" and statement.startswith("UPDATE async_tasks"):
            competing.set()

    def operation(status):
        try:
            if status == "cancelled":
                cancel(service)
            else:
                service._finish("exp", "owner", "completed", output_dir=str(tmp_path))
        except Exception as exc:
            errors.append(exc)

    event.listen(service._engine, "before_cursor_execute", hold_first_writer)
    first = Thread(target=operation, args=(winner,), name="first")
    second = Thread(
        target=operation,
        args=("completed" if winner == "cancelled" else "cancelled",),
        name="second",
    )
    try:
        first.start()
        assert entered.wait(10)
        second.start()
        assert competing.wait(10)
    finally:
        release.set()
        first.join(10)
        if second.ident is not None:
            second.join(10)
        event.remove(service._engine, "before_cursor_execute", hold_first_writer)
    assert not first.is_alive() and not second.is_alive()
    if winner == "completed":
        assert len(errors) == 1 and isinstance(errors[0], ValueError)
        assert "Cannot cancel" in str(errors[0])
    else:
        assert errors == []
    with service._session() as db:
        task, experiment = db.get(AsyncTask, "task"), db.get(Experiment, "exp")
        assert task.status == experiment.status == winner
        assert task.completed_at is not None
        assert task.completed_at == experiment.completed_at
        assert experiment.output_dir == (str(tmp_path) if winner == "completed" else None)
