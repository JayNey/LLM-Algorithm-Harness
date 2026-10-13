"""Tests for the benchmark Celery task."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, BenchmarkRun, BenchmarkSuite
from src.tasks.benchmark import run_benchmark_task


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
