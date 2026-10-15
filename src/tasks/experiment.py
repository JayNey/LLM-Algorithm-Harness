"""Celery task that runs one persisted experiment."""

from __future__ import annotations

from typing import Any

from celery import Task
from sqlalchemy.orm import Session

from api.db.models import AsyncTask, Experiment, utcnow
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session, owned_async_task


def execute_experiment(experiment_id: str, user_id: str) -> None:
    """Run an experiment that the caller has already marked running."""
    from api.services.experiment_service import ExperimentService

    ExperimentService(recover=False)._execute(experiment_id, user_id)


def _is_paused(db: Session, task_id: str) -> bool:
    current = db.query(AsyncTask).populate_existing().filter(AsyncTask.id == task_id).first()
    return current is not None and current.status == "paused"


def _keep_paused(db: Session, experiment_id: str) -> None:
    experiment = db.get(Experiment, experiment_id)
    if experiment is not None and experiment.status == "running":
        experiment.status = "paused"
        experiment.updated_at = utcnow()
        db.commit()


class ExperimentTask(Task):  # type: ignore[misc]
    """Experiment task base used to keep the Celery class typed."""


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=ExperimentTask,
    name="src.tasks.experiment.run_experiment_task",
    acks_late=True,
)
def run_experiment_task(self: ExperimentTask, experiment_id: str, user_id: str) -> dict[str, Any]:
    """Execute a pending experiment and mirror its final status onto the async task."""
    db = get_db_session()
    try:
        async_task = owned_async_task(db, "experiment", experiment_id, user_id)
        manager = TaskManager(db)
        experiment = db.get(Experiment, experiment_id)
        if experiment is None or experiment.user_id != user_id:
            message = f"Experiment {experiment_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        if experiment.status != "pending":
            message = f"Cannot start experiment in {experiment.status} status"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)

        experiment.status = "running"
        experiment.started_at = utcnow()
        experiment.updated_at = utcnow()
        db.commit()
        manager.update_task_status(async_task.id, "running")
        try:
            execute_experiment(experiment_id, user_id)
        except Exception as exc:
            db.rollback()
            if _is_paused(db, async_task.id):
                _keep_paused(db, experiment_id)
                return {"experiment_id": experiment_id, "status": "paused"}
            experiment = db.get(Experiment, experiment_id)
            if experiment is not None and experiment.status not in (
                "completed",
                "failed",
                "cancelled",
                "paused",
            ):
                experiment.status = "failed"
                experiment.error_message = str(exc)
                experiment.updated_at = utcnow()
                db.commit()
            manager.update_task_status(async_task.id, "failed", error_message=str(exc))
            raise

        db.expire_all()
        experiment = db.get(Experiment, experiment_id)
        if experiment is None:
            message = f"Experiment {experiment_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        if _is_paused(db, async_task.id) or experiment.status == "paused":
            _keep_paused(db, experiment_id)
            return {"experiment_id": experiment_id, "status": "paused"}
        status = (
            experiment.status
            if experiment.status in ("completed", "failed", "cancelled")
            else "failed"
        )
        manager.update_task_status(
            async_task.id,
            status,
            error_message=experiment.error_message,
        )
        return {"experiment_id": experiment_id, "status": status}
    finally:
        db.close()
