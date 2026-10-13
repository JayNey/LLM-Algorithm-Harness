"""Tests for the experiment Celery task."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Experiment
from src.tasks.experiment import run_experiment_task


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


def _seed(db_session, *, with_experiment: bool = True):
    experiment_id = str(uuid.uuid4())
    user_id = "owner-1"
    db_session.add(
        AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=f"celery-{experiment_id}",
            task_type="experiment",
            entity_id=experiment_id,
            user_id=user_id,
            status="pending",
        )
    )
    if with_experiment:
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
    return experiment_id, user_id


def test_experiment_task_is_registered_on_default_queue():
    from src.celery_app import celery_app

    celery_app.loader.import_default_modules()
    assert "src.tasks.experiment" in celery_app.conf.include
    assert "src.tasks.experiment.run_experiment_task" in celery_app.tasks
    assert celery_app.conf.task_routes["src.tasks.experiment.*"]["queue"] == "default"


def test_run_experiment_task_success(db_session):
    experiment_id, user_id = _seed(db_session)

    def finish(experiment_id: str, user_id: str) -> None:
        row = db_session.get(Experiment, experiment_id)
        assert row is not None and row.status == "running"
        row.status = "completed"
        db_session.commit()

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch("src.tasks.experiment.execute_experiment", side_effect=finish),
    ):
        result = run_experiment_task(experiment_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    assert result["status"] == "completed"
    assert task.status == "completed"
    assert check.get(Experiment, experiment_id).status == "completed"
    check.close()


def test_run_experiment_task_failure_records_error(db_session):
    experiment_id, user_id = _seed(db_session)

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch(
            "src.tasks.experiment.execute_experiment",
            side_effect=RuntimeError("runner exploded"),
        ),
    ):
        with pytest.raises(RuntimeError, match="runner exploded"):
            run_experiment_task(experiment_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    experiment = check.get(Experiment, experiment_id)
    assert task.status == "failed"
    assert task.error_message == "runner exploded"
    assert experiment.status == "failed"
    assert experiment.error_message == "runner exploded"
    check.close()


def test_run_experiment_task_missing_experiment(db_session):
    experiment_id, user_id = _seed(db_session, with_experiment=False)

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch("src.tasks.experiment.execute_experiment") as execute,
    ):
        with pytest.raises(ValueError, match="not found"):
            run_experiment_task(experiment_id, user_id)

    execute.assert_not_called()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    assert task.status == "failed"
    assert "not found" in task.error_message
    check.close()
