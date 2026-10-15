"""Tests for the experiment Celery task."""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Experiment
from src.tasks.experiment import execute_experiment, run_experiment_task


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


def test_run_experiment_task_rejects_other_users_experiment(db_session):
    experiment_id, user_id = _seed(db_session)
    experiment = db_session.get(Experiment, experiment_id)
    assert experiment is not None
    experiment.user_id = "someone-else"
    db_session.commit()

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch("src.tasks.experiment.execute_experiment") as execute,
    ):
        with pytest.raises(ValueError, match="not found"):
            run_experiment_task(experiment_id, user_id)

    execute.assert_not_called()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    row = check.get(Experiment, experiment_id)
    assert task.status == "failed"
    assert "not found" in task.error_message
    assert row.status == "pending"
    check.close()


def test_run_experiment_task_rejects_non_pending(db_session):
    experiment_id, user_id = _seed(db_session)
    experiment = db_session.get(Experiment, experiment_id)
    assert experiment is not None
    experiment.status = "running"
    db_session.commit()

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch("src.tasks.experiment.execute_experiment") as execute,
    ):
        with pytest.raises(ValueError, match="Cannot start experiment"):
            run_experiment_task(experiment_id, user_id)

    execute.assert_not_called()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    assert task.status == "failed"
    assert "running" in task.error_message
    check.close()


def test_execute_experiment_disables_recovery():
    with patch("api.services.experiment_service.ExperimentService") as service_cls:
        execute_experiment("exp-1", "owner-1")

    service_cls.assert_called_once_with(recover=False)
    service_cls.return_value._execute.assert_called_once_with("exp-1", "owner-1")


def test_run_experiment_task_keeps_paused_status(db_session):
    experiment_id, user_id = _seed(db_session)

    def pause(experiment_id: str, user_id: str) -> None:
        other = _reload(db_session)
        row = other.get(Experiment, experiment_id)
        task = other.query(AsyncTask).filter_by(entity_id=experiment_id).one()
        assert row is not None and row.status == "running"
        row.status = "paused"
        task.status = "paused"
        other.commit()
        other.close()

    with (
        patch("src.tasks.experiment.get_db_session", return_value=db_session),
        patch("src.tasks.experiment.execute_experiment", side_effect=pause),
    ):
        result = run_experiment_task(experiment_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=experiment_id).one()
    assert result["status"] == "paused"
    assert task.status == "paused"
    assert check.get(Experiment, experiment_id).status == "paused"
    check.close()


def test_runner_skips_later_combinations_after_pause(tmp_path):
    from types import SimpleNamespace

    from src.experiment import ExperimentRunner
    from src.models import ExperimentConfig, LLMConfig, StrategyConfig

    engine = create_engine(f"sqlite:///{tmp_path}/biz.sqlite3")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    task = AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id="celery-pause",
        task_type="experiment",
        entity_id="exp-pause",
        user_id="owner-1",
        status="running",
    )
    session.add(task)
    session.commit()
    task_id = task.id
    calls = []

    def combo(_self, _exp_dir, _model, _strategy, repeat):
        calls.append(repeat)
        other = sessionmaker(bind=engine)()
        row = other.get(AsyncTask, task_id)
        assert row is not None
        row.status = "paused"
        other.commit()
        other.close()
        return {"repeat": repeat}

    config = ExperimentConfig(
        name="pause",
        dataset_path="problems.json",
        output_dir=str(tmp_path),
        models=[LLMConfig(provider="openai", api_key="sk-test", model="demo")],
        strategies=[StrategyConfig(name="vanilla")],
        repeats=2,
        execution="serial",
    )
    runner = ExperimentRunner(config)
    runner.pricing_manager = SimpleNamespace(
        get_pricing=lambda _model: SimpleNamespace(to_dict=lambda: {})
    )

    def paused() -> bool:
        other = sessionmaker(bind=engine)()
        try:
            row = other.query(AsyncTask).populate_existing().filter_by(id=task_id).one()
            return row.status == "paused"
        finally:
            other.close()

    runner.should_pause = paused
    with (
        patch.object(ExperimentRunner, "_load_problems", return_value=[object()]),
        patch.object(ExperimentRunner, "_create_experiment_dir", return_value=tmp_path),
        patch.object(ExperimentRunner, "_dataset_fingerprint", return_value={}),
        patch.object(ExperimentRunner, "_run_combo", autospec=True, side_effect=combo),
    ):
        runner.run()

    assert calls == [1]
    assert runner.paused is True
    session.close()


def test_execute_marks_experiment_paused_from_other_connection(tmp_path):
    from api.services.experiment_service import ExperimentService

    service = ExperimentService(f"sqlite:///{tmp_path}/biz.sqlite3", recover=False)
    experiment_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            Experiment(
                id=experiment_id,
                user_id="owner-1",
                name="budget",
                status="running",
                config={"name": "budget"},
            )
        )
        session.add(
            AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id="celery-pause",
                task_type="experiment",
                entity_id=experiment_id,
                user_id="owner-1",
                status="running",
            )
        )
        session.commit()

    class Runner:
        def __init__(self):
            self.should_pause = None
            self.paused = False

        def run(self):
            other = sessionmaker(bind=service._engine)()
            row = other.query(AsyncTask).one()
            row.status = "paused"
            other.commit()
            other.close()
            self.paused = bool(self.should_pause and self.should_pause())
            return tmp_path

    service._runner_factory = lambda _config: Runner()
    with patch.object(service, "_build_runner_config", return_value=object()):
        service._execute(experiment_id, "owner-1")

    with service._session() as session:
        assert session.get(Experiment, experiment_id).status == "paused"
