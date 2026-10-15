"""Tests for the benchmark Celery task."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, BenchmarkRun, BenchmarkSuite
from src.tasks.benchmark import execute_benchmark, run_benchmark_task


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    session.info["engine"] = engine
    yield session
    session.close()


def _reload(db_session):
    return sessionmaker(bind=db_session.info["engine"])()


def _seed(db_session):
    user_id = "owner-1"
    suite_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    db_session.add(
        BenchmarkSuite(
            id=suite_id,
            user_id=user_id,
            name=f"suite-{suite_id[:8]}",
            problems=["p1"],
        )
    )
    db_session.add(
        BenchmarkRun(
            id=run_id,
            suite_id=suite_id,
            user_id=user_id,
            status="pending",
            model="demo",
            config={"model": "demo"},
        )
    )
    db_session.add(
        AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=f"celery-{run_id}",
            task_type="benchmark",
            entity_id=run_id,
            user_id=user_id,
            status="pending",
        )
    )
    db_session.commit()
    return run_id, user_id


def test_benchmark_task_is_registered_on_default_queue():
    from src.celery_app import celery_app

    celery_app.loader.import_default_modules()
    assert "src.tasks.benchmark" in celery_app.conf.include
    assert "src.tasks.benchmark.run_benchmark_task" in celery_app.tasks
    assert celery_app.conf.task_routes["src.tasks.benchmark.*"]["queue"] == "default"


def test_run_benchmark_task_completed_records_metrics(db_session):
    run_id, user_id = _seed(db_session)

    def finish(run_id: str, user_id: str) -> None:
        row = db_session.get(BenchmarkRun, run_id)
        assert row is not None
        row.status = "completed"
        row.accuracy = 0.75
        row.cost_usd = 1.25
        db_session.commit()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark", side_effect=finish),
    ):
        result = run_benchmark_task(run_id, user_id)

    check = _reload(db_session)
    run = check.get(BenchmarkRun, run_id)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    assert result["status"] == "completed"
    assert run.status == "completed"
    assert run.accuracy == 0.75
    assert run.cost_usd == 1.25
    assert task.status == "completed"
    check.close()


def test_run_benchmark_task_failure_records_error(db_session):
    run_id, user_id = _seed(db_session)

    def fail(run_id: str, user_id: str) -> None:
        row = db_session.get(BenchmarkRun, run_id)
        assert row is not None
        row.status = "failed"
        row.error_message = "executor failed"
        db_session.commit()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark", side_effect=fail),
    ):
        result = run_benchmark_task(run_id, user_id)

    check = _reload(db_session)
    run = check.get(BenchmarkRun, run_id)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    assert result["status"] == "failed"
    assert run.status == "failed"
    assert task.status == "failed"
    assert task.error_message == "executor failed"
    check.close()


def test_run_benchmark_task_cancel_does_not_complete(db_session):
    run_id, user_id = _seed(db_session)

    def cancel(run_id: str, user_id: str) -> None:
        row = db_session.get(BenchmarkRun, run_id)
        task = db_session.query(AsyncTask).filter_by(entity_id=run_id).one()
        assert row is not None
        row.status = "cancelled"
        task.status = "cancelled"
        db_session.commit()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark", side_effect=cancel),
    ):
        result = run_benchmark_task(run_id, user_id)

    check = _reload(db_session)
    run = check.get(BenchmarkRun, run_id)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    assert result["status"] == "cancelled"
    assert run.status == "cancelled"
    assert task.status == "cancelled"
    check.close()


def test_run_benchmark_task_rejects_other_users_run(db_session):
    run_id, user_id = _seed(db_session)
    run = db_session.get(BenchmarkRun, run_id)
    assert run is not None
    run.user_id = "someone-else"
    db_session.commit()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark") as execute,
    ):
        with pytest.raises(ValueError, match="not found"):
            run_benchmark_task(run_id, user_id)

    execute.assert_not_called()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    row = check.get(BenchmarkRun, run_id)
    assert task.status == "failed"
    assert "not found" in task.error_message
    assert row.status == "pending"
    check.close()


def test_run_benchmark_task_rejects_non_pending(db_session):
    run_id, user_id = _seed(db_session)
    run = db_session.get(BenchmarkRun, run_id)
    assert run is not None
    run.status = "running"
    db_session.commit()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark") as execute,
    ):
        with pytest.raises(ValueError, match="Cannot start benchmark"):
            run_benchmark_task(run_id, user_id)

    execute.assert_not_called()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    assert task.status == "failed"
    assert "running" in task.error_message
    check.close()


def test_execute_benchmark_disables_recovery():
    with patch("api.services.benchmark_service.BenchmarkService") as service_cls:
        execute_benchmark("run-1", "owner-1")

    service_cls.assert_called_once_with(recover=False)
    service_cls.return_value._execute.assert_called_once_with("run-1", "owner-1")


def test_run_benchmark_task_keeps_paused_status(db_session):
    run_id, user_id = _seed(db_session)

    def pause(run_id: str, user_id: str) -> None:
        other = _reload(db_session)
        run = other.get(BenchmarkRun, run_id)
        task = other.query(AsyncTask).filter_by(entity_id=run_id).one()
        assert run is not None
        run.status = "paused"
        task.status = "paused"
        other.commit()
        other.close()

    with (
        patch("src.tasks.benchmark.get_db_session", return_value=db_session),
        patch("src.tasks.benchmark.execute_benchmark", side_effect=pause),
    ):
        result = run_benchmark_task(run_id, user_id)

    check = _reload(db_session)
    run = check.get(BenchmarkRun, run_id)
    task = check.query(AsyncTask).filter_by(entity_id=run_id).one()
    assert result["status"] == "paused"
    assert run.status == "paused"
    assert task.status == "paused"
    check.close()


def test_execute_marks_benchmark_paused_from_other_connection(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from api.services.benchmark_service import BenchmarkService
    from src.models import LLMConfig

    dataset = tmp_path / "problems.json"
    dataset.write_text("[]", encoding="utf-8")
    service = BenchmarkService(f"sqlite:///{tmp_path}/biz.sqlite3", recover=False)
    run_id = str(uuid.uuid4())
    suite_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            BenchmarkSuite(
                id=suite_id,
                user_id="owner-1",
                name=f"suite-{suite_id[:8]}",
                problems=["first", "second"],
            )
        )
        session.flush()
        session.add(
            BenchmarkRun(
                id=run_id,
                suite_id=suite_id,
                user_id="owner-1",
                status="pending",
                model="demo",
                config={
                    "api_key_id": "key-1",
                    "model": "demo",
                    "dataset_path": str(dataset),
                    "strategies": [],
                },
            )
        )
        session.add(
            AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id="celery-pause",
                task_type="benchmark",
                entity_id=run_id,
                user_id="owner-1",
                status="running",
            )
        )
        session.commit()

    calls: list[str] = []

    class Executor:
        def __init__(self, suite, config):
            self.should_pause = None
            self.paused = False

        def execute(self):
            other = sessionmaker(bind=service._engine)()
            row = other.query(AsyncTask).one()
            row.status = "paused"
            other.commit()
            other.close()
            if not (self.should_pause and self.should_pause()):
                calls.append("first")
            calls.append("checked")
            self.paused = bool(self.should_pause and self.should_pause())
            return {}

    service._auth = SimpleNamespace(
        llm_config=lambda *_args, **_kwargs: LLMConfig(
            provider="openai", api_key="sk-test", model="demo"
        )
    )
    service._executor_factory = Executor
    monkeypatch.setattr("api.services.benchmark_service.resolve_dataset_path", lambda raw: dataset)
    service._execute(run_id, "owner-1")

    assert calls == ["checked"]
    with service._session() as session:
        assert session.get(BenchmarkRun, run_id).status == "paused"


def test_execute_records_percentage_and_current_step(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from sqlalchemy.orm import sessionmaker

    from api.services.benchmark_service import BenchmarkService
    from src.models import LLMConfig

    dataset = tmp_path / "problems.json"
    dataset.write_text("[]", encoding="utf-8")
    service = BenchmarkService(f"sqlite:///{tmp_path}/biz.sqlite3", recover=False)
    run_id = str(uuid.uuid4())
    suite_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            BenchmarkSuite(
                id=suite_id,
                user_id="owner-1",
                name=f"suite-{suite_id[:8]}",
                problems=["two-sum", "second"],
            )
        )
        session.flush()
        session.add(
            BenchmarkRun(
                id=run_id,
                suite_id=suite_id,
                user_id="owner-1",
                status="pending",
                model="demo",
                config={
                    "api_key_id": "key-1",
                    "model": "demo",
                    "dataset_path": str(dataset),
                    "strategies": [{"name": "vanilla"}],
                },
            )
        )
        session.add(
            AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id="celery-progress",
                task_type="benchmark",
                entity_id=run_id,
                user_id="owner-1",
                status="running",
            )
        )
        session.commit()

    seen: list[dict] = []

    class Executor:
        def __init__(self, suite, config):
            self.should_pause = None
            self.on_problem = None
            self.paused = False

        def execute(self):
            assert self.on_problem is not None
            self.on_problem(0, 2, "vanilla", "two-sum")
            other = sessionmaker(bind=service._engine)()
            try:
                seen.append(dict(other.query(AsyncTask).one().progress))
            finally:
                other.close()
            self.on_problem(1, 2, "vanilla", "second")
            return {"accuracy": 1.0, "cost_usd": 0.0, "summary": {}}

    service._auth = SimpleNamespace(
        llm_config=lambda *_args, **_kwargs: LLMConfig(
            provider="openai", api_key="sk-test", model="demo"
        )
    )
    service._executor_factory = Executor
    monkeypatch.setattr("api.services.benchmark_service.resolve_dataset_path", lambda raw: dataset)
    service._execute(run_id, "owner-1")

    with service._session() as session:
        progress = dict(session.query(AsyncTask).one().progress)
    assert seen[0]["current_step"] == "vanilla/two-sum"
    assert seen[0]["percentage"] == 0
    assert progress["current_step"] == "vanilla/second"
    assert progress["percentage"] == 50
    assert 0 <= progress["percentage"] <= 100
    assert "hidden problem body" not in progress["current_step"]
