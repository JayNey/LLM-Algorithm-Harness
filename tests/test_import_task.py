"""Tests for the import Celery task."""

import uuid
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base
from src.tasks.imports import execute_import, run_import_task


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
    job_id = str(uuid.uuid4())
    user_id = "owner-1"
    db_session.add(
        AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=f"celery-{job_id}",
            task_type="import",
            entity_id=job_id,
            user_id=user_id,
            status="pending",
        )
    )
    db_session.commit()
    return job_id, user_id


def test_import_task_is_registered_on_default_queue():
    from src.celery_app import celery_app

    celery_app.loader.import_default_modules()
    assert "src.tasks.imports" in celery_app.conf.include
    assert "src.tasks.imports.run_import_task" in celery_app.tasks
    assert celery_app.conf.task_routes["src.tasks.imports.*"]["queue"] == "default"


def test_execute_import_missing_job_does_not_process():
    with (
        patch("api.auth.config.AuthSettings"),
        patch("api.auth.service.AuthService"),
        patch("api.files.config.FileSettings"),
        patch("api.files.service.FileService") as service_cls,
    ):
        service = service_cls.return_value
        service.store.job.side_effect = HTTPException(404, "Import job not found")
        with pytest.raises(ValueError, match="not found"):
            execute_import("missing", "other-user")
        service.process_job.assert_not_called()


def test_run_import_task_reports_progress_and_completes(db_session):
    job_id, user_id = _seed(db_session)

    def finish(job_id: str, user_id: str, on_progress, should_pause=None) -> dict:
        on_progress(2, 4)
        return {"status": "completed", "processed": 4, "total": 4, "result": None}

    with (
        patch("src.tasks.imports.get_db_session", return_value=db_session),
        patch("src.tasks.imports.execute_import", side_effect=finish),
    ):
        result = run_import_task(job_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=job_id).one()
    assert result["status"] == "completed"
    assert task.status == "completed"
    assert task.progress["current"] == 2
    assert task.progress["total"] == 4
    assert task.progress["percentage"] == 50
    assert task.progress["current_step"] == "2"
    assert 0 <= task.progress["percentage"] <= 100
    assert "hidden problem body" not in str(task.progress)
    check.close()


def test_run_import_task_missing_job_does_not_continue(db_session):
    job_id, user_id = _seed(db_session)

    with (
        patch("src.tasks.imports.get_db_session", return_value=db_session),
        patch(
            "src.tasks.imports.execute_import",
            side_effect=ValueError(f"Import job {job_id} not found"),
        ) as execute,
    ):
        with pytest.raises(ValueError, match="not found"):
            run_import_task(job_id, user_id)

    execute.assert_called_once()
    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=job_id).one()
    assert task.status == "failed"
    assert "current" not in task.progress
    check.close()


def test_run_import_task_failure_records_result_detail(db_session):
    job_id, user_id = _seed(db_session)

    def finish(job_id: str, user_id: str, on_progress, should_pause=None) -> dict:
        return {"status": "failed", "result": {"detail": "row 3 is invalid"}}

    with (
        patch("src.tasks.imports.get_db_session", return_value=db_session),
        patch("src.tasks.imports.execute_import", side_effect=finish),
    ):
        result = run_import_task(job_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=job_id).one()
    assert result["status"] == "failed"
    assert task.status == "failed"
    assert task.error_message == "row 3 is invalid"
    check.close()


def test_run_import_task_keeps_paused_status(db_session):
    job_id, user_id = _seed(db_session)

    def pause(job_id: str, user_id: str, on_progress, should_pause=None) -> dict:
        other = _reload(db_session)
        task = other.query(AsyncTask).filter_by(entity_id=job_id).one()
        task.status = "paused"
        other.commit()
        other.close()
        return {"status": "paused", "result": None}

    with (
        patch("src.tasks.imports.get_db_session", return_value=db_session),
        patch("src.tasks.imports.execute_import", side_effect=pause),
    ):
        result = run_import_task(job_id, user_id)

    check = _reload(db_session)
    task = check.query(AsyncTask).filter_by(entity_id=job_id).one()
    assert result["status"] == "paused"
    assert task.status == "paused"
    check.close()
