"""Celery task that runs one persisted experiment."""

from __future__ import annotations

from typing import Any

from celery import Task

from api.db.models import Experiment
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session, owned_async_task


def execute_experiment(experiment_id: str, user_id: str) -> None:
    """Run an experiment that the caller has already marked running."""
    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from api.services.experiment_service import ExperimentService

    service = ExperimentService(auth=AuthService(AuthSettings()), recover=False)
    try:
        service._execute(experiment_id, user_id)
    finally:
        service._engine.dispose()


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
        manager._lock_business_task(async_task)
        if async_task.status in ("paused", "cancelled", "completed", "failed"):
            return {"experiment_id": experiment_id, "status": async_task.status}
        experiment = db.get(Experiment, experiment_id, populate_existing=True)
        if experiment is None or experiment.user_id != user_id:
            message = f"Experiment {experiment_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        if experiment.status != "pending":
            message = f"Cannot start experiment in {experiment.status} status"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)

        manager.update_task_status(async_task.id, "running")
        try:
            execute_experiment(experiment_id, user_id)
        except Exception as exc:
            db.rollback()
            manager.update_task_status(async_task.id, "failed", error_message=str(exc))
            db.refresh(async_task)
            if async_task.status in ("paused", "cancelled", "completed"):
                return {"experiment_id": experiment_id, "status": async_task.status}
            raise

        db.expire_all()
        manager._lock_business_task(async_task)
        if async_task.status in ("paused", "cancelled", "completed", "failed"):
            return {"experiment_id": experiment_id, "status": async_task.status}
        experiment = db.get(Experiment, experiment_id, populate_existing=True)
        if experiment is None or experiment.user_id != user_id:
            message = f"Experiment {experiment_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        status = (
            experiment.status
            if experiment.status in ("completed", "failed", "cancelled", "paused")
            else "failed"
        )
        manager.update_task_status(
            async_task.id,
            status,
            error_message=experiment.error_message,
        )
        db.refresh(async_task)
        return {"experiment_id": experiment_id, "status": async_task.status}
    finally:
        db.close()
