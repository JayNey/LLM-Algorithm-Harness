"""Resume contracts against real independent database sessions (issue #306)."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from api.auth.store import AuthStore
from api.db.engine import make_engine
from api.db.models import (
    ABTest,
    AsyncTask,
    Base,
    BenchmarkRun,
    BenchmarkSuite,
    Evaluation,
    Experiment,
)
from api.files.store import FileStore
from src.task_manager import TaskManager

KINDS = ("experiment", "benchmark", "import", "ab_test", "evaluation")


@pytest.fixture
def resumedb(tmp_path, monkeypatch):
    engine = make_engine(f"sqlite:///{tmp_path}/business.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    path = tmp_path / "auth.db"
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(path))
    store = FileStore(AuthStore(path))
    yield factory, store
    engine.dispose()


def seed(factory, store, kind, *, status="paused", confirmed=True):
    with factory() as db:
        task = AsyncTask(
            id="task",
            entity_id="entity",
            user_id="owner",
            task_type=kind,
            celery_task_id="old-message",
            status=status,
            progress={"current": 1, "total": 3, "stop_confirmed": confirmed},
        )
        db.add(task)
        if kind == "experiment":
            db.add(Experiment(id="entity", user_id="owner", status=status, config={}))
        elif kind == "ab_test":
            db.add(ABTest(id="entity", user_id="owner", status=status, config={}))
        elif kind == "benchmark":
            db.add(BenchmarkSuite(id="suite", user_id="owner", name="suite", problems=[]))
            db.flush()
            db.add(
                BenchmarkRun(
                    id="entity",
                    suite_id="suite",
                    user_id="owner",
                    status=status,
                    cost_usd=1.25,
                    results={"saved": True},
                )
            )
        elif kind == "evaluation":
            db.flush()
            db.add(
                Evaluation(
                    id="entity",
                    user_id="owner",
                    status=status,
                    async_task_id="task",
                    completed_count=1,
                    spent_usd=1.25,
                )
            )
        elif kind == "import":
            with store.connection() as conn:
                conn.execute(
                    "INSERT INTO api_file_jobs(id,user_id,file_id,mode,status,processed,total,created_at,updated_at) VALUES ('entity','owner','file','append',?,1,3,0,0)",
                    (status,),
                )
        db.commit()


def business_status(db, store, kind):
    if kind == "import":
        return store.job("entity", "owner")["status"]
    model = {
        "experiment": Experiment,
        "benchmark": BenchmarkRun,
        "ab_test": ABTest,
        "evaluation": Evaluation,
    }[kind]
    return db.get(model, "entity", populate_existing=True).status


@pytest.mark.parametrize("kind", KINDS)
def test_resume_commits_pair_before_publish_and_preserves_progress(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind)
    published = []

    def publish(name, *, args, task_id):
        with factory() as check:
            row = check.get(AsyncTask, "task")
            assert row.status == business_status(check, store, kind) == "pending"
            assert row.celery_task_id == task_id != "old-message"
            assert row.progress["current"] == 1
            assert args == (("entity",) if kind == "evaluation" else ("entity", "owner"))
            published.append(name)

    with factory() as db, patch("src.task_manager.celery_app.send_task", side_effect=publish):
        row = TaskManager(db).resume_task("task", "owner")
        assert row.id == "task"
    assert len(published) == 1
    with factory() as db:
        if kind == "benchmark":
            assert db.get(BenchmarkRun, "entity").cost_usd == 1.25
            assert db.get(BenchmarkRun, "entity").results == {"saved": True}
        if kind == "evaluation":
            assert db.get(Evaluation, "entity").spent_usd == 1.25


@pytest.mark.parametrize("kind", KINDS)
def test_concurrent_resume_only_publishes_one_message(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind)

    def resume(_):
        with factory() as db:
            try:
                TaskManager(db).resume_task("task", "owner")
                return True
            except ValueError:
                return False

    with patch("src.task_manager.celery_app.send_task") as publish:
        with ThreadPoolExecutor(max_workers=2) as pool:
            outcomes = list(pool.map(resume, range(2)))
    assert outcomes.count(True) == 1
    assert publish.call_count == 1


@pytest.mark.parametrize("kind", KINDS)
def test_resume_publish_failure_updates_pair(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind)
    with (
        factory() as db,
        patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")),
    ):
        with pytest.raises(RuntimeError, match="broker down"):
            TaskManager(db).resume_task("task", "owner")
    with factory() as db:
        row = db.get(AsyncTask, "task")
        assert row.status == business_status(db, store, kind) == "failed"
        assert row.completed_at is not None
        assert row.progress["current"] == 1


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("winner", ["running", "cancelled", "completed"])
def test_publish_timeout_preserves_competing_state(resumedb, kind, winner):
    factory, store = resumedb
    seed(factory, store, kind)

    def publish(*args, **kwargs):
        with factory() as db:
            TaskManager(db).update_task_status("task", winner)
        raise RuntimeError("timeout after delivery")

    with factory() as db, patch("src.task_manager.celery_app.send_task", side_effect=publish):
        with pytest.raises(RuntimeError):
            TaskManager(db).resume_task("task", "owner")
    with factory() as db:
        assert db.get(AsyncTask, "task").status == business_status(db, store, kind) == winner


@pytest.mark.parametrize("kind", KINDS[:-1])
def test_pause_requires_worker_stop_confirmation(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind, status="running")
    with factory() as db, patch("src.task_manager.celery_app.AsyncResult"):
        manager = TaskManager(db)
        manager.pause_task("task", "owner")
        assert business_status(db, store, kind) == "paused"
        with pytest.raises(ValueError, match="stopp"):
            manager.resume_task("task", "owner")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "cancelled"])
def test_nonpaused_and_other_owner_cannot_resume(resumedb, kind, status):
    factory, store = resumedb
    seed(factory, store, kind, status=status)
    with (
        factory() as db,
        patch("src.task_manager.celery_app.AsyncResult"),
        patch("src.task_manager.celery_app.send_task") as publish,
    ):
        with pytest.raises(ValueError):
            TaskManager(db).resume_task("task", "owner")
        with pytest.raises(ValueError):
            TaskManager(db).resume_task("task", "intruder")
        assert db.get(AsyncTask, "task").status == status
        publish.assert_not_called()


@pytest.mark.parametrize("kind", KINDS[:-1])
def test_claim_is_unique_and_old_callbacks_cannot_change_resumed_task(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind, status="pending")
    with factory() as db:
        manager = TaskManager(db, celery_task_id="old-message")
        assert manager.claim_task("task", "old-message")
        assert not manager.claim_task("task", "old-message")
    with factory() as db, patch("src.task_manager.celery_app.AsyncResult"):
        TaskManager(db).pause_task("task", "owner")
    with factory() as db:
        TaskManager(db, celery_task_id="old-message").confirm_stopped("task")
    with factory() as db, patch("src.task_manager.celery_app.send_task"):
        new = TaskManager(db).resume_task("task", "owner").celery_task_id
    with factory() as db:
        stale = TaskManager(db, celery_task_id="old-message")
        assert not stale.claim_task("task", "old-message")
        stale.update_task_progress("task", {"current": 99}, "running")
        stale.update_task_status("task", "failed", "old failure")
        stale.confirm_stopped("task")
    with factory() as db:
        row = db.get(AsyncTask, "task")
        assert row.status == business_status(db, store, kind) == "pending"
        assert row.celery_task_id == new
        assert row.progress["current"] == 1
        assert row.error_message is None
        assert TaskManager(db, celery_task_id=new).claim_task("task", new)


@pytest.mark.parametrize("kind", ["experiment", "benchmark", "import"])
def test_worker_stops_confirms_resumes_and_ignores_old_delivery(resumedb, kind):
    import importlib

    factory, store = resumedb
    seed(factory, store, kind, status="pending")
    module = importlib.import_module(
        "src.tasks.imports" if kind == "import" else f"src.tasks.{kind}"
    )
    worker = getattr(
        module,
        {
            "experiment": "run_experiment_task",
            "benchmark": "run_benchmark_task",
            "import": "run_import_task",
        }[kind],
    )
    executed = []

    def execute(*args, **kwargs):
        executed.append(1)
        with factory() as db, patch("src.task_manager.celery_app.AsyncResult"):
            if len(executed) == 1:
                TaskManager(db).pause_task("task", "owner")
                return {"status": "paused"}
            if kind == "experiment":
                db.get(Experiment, "entity").status = "completed"
            elif kind == "benchmark":
                row = db.get(BenchmarkRun, "entity")
                row.status = "completed"
                row.cost_usd = 2.0
            db.commit()
            return {"status": "completed"}

    def deliver(message):
        worker.push_request(id=message)
        try:
            return worker.run("entity", "owner")
        finally:
            worker.pop_request()

    executor = {
        "experiment": "execute_experiment",
        "benchmark": "execute_benchmark",
        "import": "execute_import",
    }[kind]
    with (
        patch.object(module, "get_db_session", side_effect=factory),
        patch.object(module, executor, side_effect=execute),
    ):
        assert deliver("old-message")["status"] == "paused"
        with factory() as db:
            assert db.get(AsyncTask, "task").progress["stop_confirmed"] is True
            assert business_status(db, store, kind) == "paused"
        with factory() as db, patch("src.task_manager.celery_app.send_task"):
            new = TaskManager(db).resume_task("task", "owner").celery_task_id
        deliver("old-message")
        assert len(executed) == 1
        assert deliver(new)["status"] == "completed"
        deliver(new)
        assert len(executed) == 2
    with factory() as db:
        assert db.get(AsyncTask, "task").status == business_status(db, store, kind) == "completed"


@pytest.mark.parametrize("kind", KINDS)
def test_old_broker_result_cannot_fail_new_generation(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind, status="pending")

    def result(old_id):
        assert old_id == "old-message"
        with factory() as db:
            task = db.get(AsyncTask, "task")
            task.celery_task_id = "new-message"
            task.status = "running"
            TaskManager(db)._sync_business(task)
            db.commit()
        return SimpleNamespace(state="FAILURE", info="old failure")

    with factory() as db, patch("src.task_manager.celery_app.AsyncResult", side_effect=result):
        TaskManager(db).get_task("task", "owner")
    with factory() as db:
        assert db.get(AsyncTask, "task").status == "running"


@pytest.mark.parametrize("action", ["pause_task", "cancel_task"])
def test_import_already_merged_cannot_be_paused_or_cancelled(resumedb, action):
    factory, store = resumedb
    seed(factory, store, "import", status="running")
    with store.connection() as conn:
        conn.execute("UPDATE api_file_jobs SET status='completed' WHERE id='entity'")
    with (
        factory() as db,
        patch("src.task_manager.celery_app.AsyncResult"),
        patch("src.task_manager.celery_app.control.revoke"),
    ):
        with pytest.raises(ValueError, match="completed"):
            getattr(TaskManager(db), action)("task", "owner")
    assert store.job("entity", "owner")["status"] == "completed"


@pytest.mark.parametrize(
    "action,status",
    [("resume_task", "paused"), ("pause_task", "running"), ("cancel_task", "running")],
)
def test_import_business_commit_failure_compensates_job_status(resumedb, action, status):
    factory, store = resumedb
    seed(factory, store, "import", status=status)
    with (
        factory() as db,
        patch("src.task_manager.celery_app.AsyncResult"),
        patch("src.task_manager.celery_app.control.revoke"),
        patch.object(db, "commit", side_effect=RuntimeError("database write failed")),
    ):
        with pytest.raises(RuntimeError, match="database write failed"):
            getattr(TaskManager(db), action)("task", "owner")
    with factory() as db:
        assert db.get(AsyncTask, "task").status == business_status(db, store, "import") == status


@pytest.mark.parametrize("kind", KINDS)
def test_resume_endpoint_accepts_all_supported_owned_types(resumedb, kind):
    from api.auth.service import Principal
    from api.routes.tasks import resume_task

    factory, store = resumedb
    seed(factory, store, kind)
    with factory() as db, patch("src.task_manager.celery_app.send_task"):
        response = resume_task(
            "task",
            Principal(user_id="owner", session_id="session"),
            TaskManager(db, file_store=store),
        )
        assert response.success
        assert response.data.id == "task"
        assert response.data.status == "pending"


@pytest.mark.parametrize("kind", KINDS)
def test_cancel_racing_resume_always_leaves_cancelled_pair(resumedb, kind):
    factory, store = resumedb
    seed(factory, store, kind)

    def operation(action):
        with factory() as db:
            try:
                getattr(TaskManager(db), action)("task", "owner")
            except ValueError:
                pass

    with (
        patch("src.task_manager.celery_app.AsyncResult"),
        patch("src.task_manager.celery_app.control.revoke"),
        patch("src.task_manager.celery_app.send_task") as publish,
        patch("src.task_manager._request_evaluation_cancel"),
    ):
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(operation, ["cancel_task", "resume_task"]))
    assert publish.call_count <= 1
    with factory() as db:
        assert db.get(AsyncTask, "task").status == business_status(db, store, kind) == "cancelled"
