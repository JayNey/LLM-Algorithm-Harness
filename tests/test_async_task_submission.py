"""TaskManager submission for experiment, import, and benchmark tasks."""

import uuid
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import Base, BenchmarkRun, BenchmarkSuite, Experiment
from src.task_manager import TaskManager


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _submit(db_session, task_type, entity_id, user_id, celery_name):
    manager = TaskManager(db_session)
    with (
        patch("src.task_manager.celery_app.send_task") as send_task,
        patch("src.task_manager.celery_app.AsyncResult") as async_result,
    ):
        send_task.return_value = Mock(id=f"celery-{entity_id}")
        async_result.return_value.state = "PENDING"
        created = manager.create_task(
            task_type=task_type,
            entity_id=entity_id,
            user_id=user_id,
            celery_task_name=celery_name,
            celery_task_args=(entity_id, user_id),
        )
        queried = manager.get_task(created.id, user_id)
    send_task.assert_called_once_with(
        celery_name,
        args=(entity_id, user_id),
        kwargs={},
    )
    return created, queried


def test_submit_experiment_returns_pending_task_id(db_session):
    experiment_id = str(uuid.uuid4())
    user_id = "owner-1"
    db_session.add(
        Experiment(
            id=experiment_id,
            user_id=user_id,
            name="budget",
            status="pending",
            config={"name": "budget"},
        )
    )
    db_session.commit()

    created, queried = _submit(
        db_session,
        "experiment",
        experiment_id,
        user_id,
        "src.tasks.experiment.run_experiment_task",
    )

    assert created.id
    assert queried.status == "pending"
    assert db_session.get(Experiment, experiment_id).status == "pending"


def test_submit_import_returns_pending_task_id(db_session):
    job_id = str(uuid.uuid4())
    user_id = "owner-1"

    created, queried = _submit(
        db_session,
        "import",
        job_id,
        user_id,
        "src.tasks.imports.run_import_task",
    )

    assert created.id
    assert queried.status == "pending"
    assert queried.entity_id == job_id


def test_submit_benchmark_returns_pending_task_id(db_session):
    user_id = "owner-1"
    suite_id = str(uuid.uuid4())
    run_id = str(uuid.uuid4())
    db_session.add(
        BenchmarkSuite(
            id=suite_id,
            user_id=user_id,
            name="suite",
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
    db_session.commit()

    created, queried = _submit(
        db_session,
        "benchmark",
        run_id,
        user_id,
        "src.tasks.benchmark.run_benchmark_task",
    )

    assert created.id
    assert queried.status == "pending"
    assert db_session.get(BenchmarkRun, run_id).status == "pending"
