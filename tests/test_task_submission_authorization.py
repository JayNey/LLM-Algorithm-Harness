"""Public task submission must never dispatch internal maintenance workers."""

from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.db.engine import get_db, make_engine, make_session_factory
from api.db.models import AsyncTask, Base, utcnow
from api.routes.tasks import router
from src.tasks.cleanup import cleanup_old_tasks, cleanup_task_count

BUSINESS_TASKS = [
    ("evaluation", "src.tasks.evaluation.run_evaluation_task"),
    ("experiment", "src.tasks.experiment.run_experiment_task"),
    ("import", "src.tasks.imports.run_import_task"),
    ("benchmark", "src.tasks.benchmark.run_benchmark_task"),
]
CLEANUP_TASKS = [
    ("src.tasks.cleanup.cleanup_old_tasks", {"days_to_keep": 0}),
    ("src.tasks.cleanup.cleanup_task_count", {"max_retention": 0}),
]


@pytest.fixture
def task_api(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'tasks.sqlite3'}")
    Base.metadata.create_all(engine)
    factory = make_session_factory(engine)

    def database():
        with factory() as session:
            yield session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: Principal(
        user_id="attacker", session_id="attacker-session"
    )
    app.dependency_overrides[get_db] = database
    with TestClient(app) as client:
        yield client, factory
    engine.dispose()


@pytest.mark.parametrize("task_type", ["cleanup", *[kind for kind, _ in BUSINESS_TASKS]])
@pytest.mark.parametrize("celery_name,kwargs", CLEANUP_TASKS)
def test_public_submission_cannot_delete_cross_user_tasks(task_api, task_type, celery_name, kwargs):
    client, factory = task_api
    original_ids = {"attacker-task", "victim-task"}
    with factory() as session, session.begin():
        for owner in ("attacker", "victim"):
            session.add(
                AsyncTask(
                    id=f"{owner}-task",
                    celery_task_id=f"celery-{owner}",
                    task_type="evaluation",
                    entity_id=f"{owner}-evaluation",
                    user_id=owner,
                    status="completed",
                    updated_at=utcnow() - timedelta(days=30),
                )
            )

    def execute_published_cleanup(name, *, args, kwargs, task_id):
        worker = cleanup_old_tasks if name == CLEANUP_TASKS[0][0] else cleanup_task_count
        with patch.object(worker, "update_state"):
            worker.__wrapped__(*args, **kwargs)

    with (
        patch("src.tasks.cleanup.get_db_session", side_effect=factory),
        patch(
            "src.task_manager.celery_app.send_task", side_effect=execute_published_cleanup
        ) as send,
    ):
        response = client.post(
            "/api/v1/tasks",
            json={
                "task_type": task_type,
                "entity_id": "attacker-entity",
                "celery_task_name": celery_name,
                "celery_task_kwargs": kwargs,
            },
        )

    with factory() as session:
        remaining_ids = {task.id for task in session.query(AsyncTask).all()}
    assert (response.status_code, send.call_count, remaining_ids) == (403, 0, original_ids)


@pytest.mark.parametrize(
    "task_type,celery_name",
    [
        ("evaluation", "src.tasks.unknown.run_task"),
        ("evaluation", "src.tasks.evaluation.cleanup_old_tasks"),
        ("evaluation", "src.tasks.experiment.run_experiment_task"),
        ("cleanup", "src.tasks.evaluation.run_evaluation_task"),
    ],
)
def test_public_submission_rejects_unknown_or_mismatched_tasks(task_api, task_type, celery_name):
    client, factory = task_api
    with patch("src.task_manager.celery_app.send_task") as send:
        response = client.post(
            "/api/v1/tasks",
            json={
                "task_type": task_type,
                "entity_id": "entity-1",
                "celery_task_name": celery_name,
            },
        )

    assert response.status_code == 403
    send.assert_not_called()
    with factory() as session:
        assert session.query(AsyncTask).count() == 0


@pytest.mark.parametrize("task_type,celery_name", BUSINESS_TASKS)
def test_public_submission_preserves_business_tasks(task_api, task_type, celery_name):
    client, factory = task_api
    args = ["entity-1"] if task_type == "evaluation" else ["entity-1", "attacker"]
    with patch("src.task_manager.celery_app.send_task", return_value=Mock()) as send:
        response = client.post(
            "/api/v1/tasks",
            json={
                "task_type": task_type,
                "entity_id": "entity-1",
                "celery_task_name": celery_name,
                "celery_task_args": args,
            },
        )

    assert response.status_code == 201
    data = response.json()["data"]
    send.assert_called_once_with(
        celery_name, args=tuple(args), kwargs={}, task_id=data["celery_task_id"]
    )
    with factory() as session:
        task = session.get(AsyncTask, data["id"])
        assert task.user_id == "attacker"
        assert task.task_type == task_type
        assert task.status == "pending"
