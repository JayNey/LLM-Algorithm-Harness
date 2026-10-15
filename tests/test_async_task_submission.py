"""TaskManager submission for experiment, import, and benchmark tasks."""

import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from api.auth.service import Principal
from api.db.engine import make_engine
from api.db.migrate import run_migrations
from api.db.models import AsyncTask, Base, BenchmarkRun, BenchmarkSuite, Experiment
from api.experiment_models import BenchmarkRunRequest
from api.models import AsyncTaskCreateRequest
from api.routes.files import ImportRequest, import_uploaded
from api.routes.tasks import create_task as create_task_route
from api.services.benchmark_service import BenchmarkService
from api.services.experiment_service import ExperimentService
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


def _visible(engine, celery_task_id: str) -> AsyncTask | None:
    """Read the task from a second connection so only a committed row is visible."""
    session = sessionmaker(bind=engine, future=True)()
    try:
        return session.scalars(
            select(AsyncTask).where(AsyncTask.celery_task_id == celery_task_id)
        ).one_or_none()
    finally:
        session.close()


def _publish_probe(engine):
    seen = {}

    def send_side_effect(*args, **kwargs):
        row = _visible(engine, kwargs["task_id"])
        seen["status"] = None if row is None else row.status
        seen["task_id"] = kwargs["task_id"]
        return Mock(id="broker-ignored")

    return seen, send_side_effect


def test_experiment_start_commits_before_publish(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    service = ExperimentService(url, recover=False)
    experiment_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            Experiment(
                id=experiment_id,
                user_id="owner-1",
                name="budget",
                status="pending",
                config={"name": "budget"},
            )
        )
        session.commit()
    seen, send_side_effect = _publish_probe(service._engine)

    with patch("src.task_manager.celery_app.send_task", side_effect=send_side_effect):
        view = service.start_experiment(experiment_id, "owner-1")

    assert seen["status"] == "pending"
    stored = _visible(service._engine, seen["task_id"])
    assert stored is not None
    assert stored.id == view["task_id"]
    assert stored.status == "pending"


def test_experiment_start_marks_failed_when_publish_raises(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    service = ExperimentService(url, recover=False)
    experiment_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            Experiment(
                id=experiment_id,
                user_id="owner-1",
                name="budget",
                status="pending",
                config={"name": "budget"},
            )
        )
        session.commit()

    with (
        patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")),
        pytest.raises(RuntimeError, match="broker down"),
    ):
        service.start_experiment(experiment_id, "owner-1")

    session = sessionmaker(bind=service._engine, future=True)()
    try:
        task = session.scalars(select(AsyncTask).where(AsyncTask.entity_id == experiment_id)).one()
    finally:
        session.close()
    assert task.status == "failed"
    assert task.error_message == "failed to publish task to broker"


def test_benchmark_start_commits_before_publish(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    auth = SimpleNamespace(owned_key=lambda key_id, owner_id: None)
    service = BenchmarkService(url, auth=auth, recover=False)
    suite_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            BenchmarkSuite(
                id=suite_id, user_id="owner-1", name=f"suite-{suite_id}", problems=["p1"]
            )
        )
        session.commit()
    seen, send_side_effect = _publish_probe(service._engine)
    request = BenchmarkRunRequest(api_key_id="key-1", dataset_path="problems.json", model="demo")

    with (
        patch(
            "api.services.benchmark_service.resolve_dataset_path",
            return_value=Path("problems.json"),
        ),
        patch("src.task_manager.celery_app.send_task", side_effect=send_side_effect),
    ):
        view = service.start_run(suite_id, request, "owner-1")

    assert seen["status"] == "pending"
    stored = _visible(service._engine, seen["task_id"])
    assert stored is not None
    assert stored.id == view["task_id"]
    assert stored.entity_id == view["id"]


def test_benchmark_start_marks_failed_when_publish_raises(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    auth = SimpleNamespace(owned_key=lambda key_id, owner_id: None)
    service = BenchmarkService(url, auth=auth, recover=False)
    suite_id = str(uuid.uuid4())
    with service._session() as session:
        session.add(
            BenchmarkSuite(
                id=suite_id, user_id="owner-1", name=f"suite-{suite_id}", problems=["p1"]
            )
        )
        session.commit()
    request = BenchmarkRunRequest(api_key_id="key-1", dataset_path="problems.json", model="demo")

    with (
        patch(
            "api.services.benchmark_service.resolve_dataset_path",
            return_value=Path("problems.json"),
        ),
        patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")),
        pytest.raises(RuntimeError, match="broker down"),
    ):
        service.start_run(suite_id, request, "owner-1")

    session = sessionmaker(bind=service._engine, future=True)()
    try:
        task = session.scalars(select(AsyncTask).where(AsyncTask.task_type == "benchmark")).one()
    finally:
        session.close()
    assert task.status == "failed"
    assert task.error_message == "failed to publish task to broker"


def test_import_route_commits_before_publish(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/biz.sqlite3")
    run_migrations(engine)
    session = sessionmaker(bind=engine, future=True)()
    service = SimpleNamespace(
        store=SimpleNamespace(create_job=lambda *args, **kwargs: "job-1"),
        settings=SimpleNamespace(FILE_MAX_ACTIVE_IMPORTS=4),
    )
    seen, send_side_effect = _publish_probe(engine)
    principal = Principal(user_id="owner-1", session_id="session-1")

    with patch("src.task_manager.celery_app.send_task", side_effect=send_side_effect):
        response = import_uploaded(ImportRequest(file_id="file-1"), principal, service, session)

    session.close()
    assert seen["status"] == "pending"
    stored = _visible(engine, seen["task_id"])
    assert stored is not None
    assert stored.id == response.data["task_id"]
    assert stored.entity_id == "job-1"


def test_import_route_marks_failed_when_publish_raises(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/biz.sqlite3")
    run_migrations(engine)
    session = sessionmaker(bind=engine, future=True)()
    service = SimpleNamespace(
        store=SimpleNamespace(create_job=lambda *args, **kwargs: "job-1"),
        settings=SimpleNamespace(FILE_MAX_ACTIVE_IMPORTS=4),
    )
    principal = Principal(user_id="owner-1", session_id="session-1")

    with (
        patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")),
        pytest.raises(RuntimeError, match="broker down"),
    ):
        import_uploaded(ImportRequest(file_id="file-1"), principal, service, session)

    session.close()
    stored = sessionmaker(bind=engine, future=True)()
    try:
        task = stored.scalars(select(AsyncTask).where(AsyncTask.entity_id == "job-1")).one()
    finally:
        stored.close()
    assert task.status == "failed"
    assert task.error_message == "failed to publish task to broker"


def test_generic_create_route_commits_before_publish(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/biz.sqlite3")
    run_migrations(engine)
    session = sessionmaker(bind=engine, future=True)()
    seen, send_side_effect = _publish_probe(engine)
    principal = Principal(user_id="owner-1", session_id="session-1")
    request = AsyncTaskCreateRequest(
        task_type="experiment",
        entity_id="exp-1",
        celery_task_name="src.tasks.experiment.run_experiment_task",
        celery_task_args=["exp-1", "owner-1"],
    )

    with patch("src.task_manager.celery_app.send_task", side_effect=send_side_effect):
        response = create_task_route(request, principal, TaskManager(session))

    session.close()
    assert seen["status"] == "pending"
    stored = _visible(engine, seen["task_id"])
    assert stored is not None
    assert stored.id == response.data.id
    assert response.data.celery_task_id == seen["task_id"]


def test_generic_create_route_marks_failed_when_publish_raises(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path}/biz.sqlite3")
    run_migrations(engine)
    session = sessionmaker(bind=engine, future=True)()
    principal = Principal(user_id="owner-1", session_id="session-1")
    request = AsyncTaskCreateRequest(
        task_type="experiment",
        entity_id="exp-1",
        celery_task_name="src.tasks.experiment.run_experiment_task",
        celery_task_args=["exp-1", "owner-1"],
    )

    with (
        patch("src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")),
        pytest.raises(RuntimeError, match="broker down"),
    ):
        create_task_route(request, principal, TaskManager(session))

    session.close()
    stored = sessionmaker(bind=engine, future=True)()
    try:
        task = stored.scalars(select(AsyncTask).where(AsyncTask.entity_id == "exp-1")).one()
    finally:
        stored.close()
    assert task.status == "failed"
    assert task.error_message == "failed to publish task to broker"
