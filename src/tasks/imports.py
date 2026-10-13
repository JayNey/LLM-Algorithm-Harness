"""Celery task that runs one uploaded dataset import."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from celery import Task
from fastapi import HTTPException

from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session, owned_async_task


def execute_import(
    job_id: str,
    user_id: str,
    on_progress: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Run an existing import job and return its stored record."""
    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from api.files.config import FileSettings
    from api.files.service import FileService

    service = FileService(AuthService(AuthSettings()), FileSettings())
    try:
        service.store.job(job_id, user_id)
    except HTTPException as exc:
        if exc.status_code == 404:
            raise ValueError(f"Import job {job_id} not found") from None
        raise
    if on_progress is not None:
        original = service.store.progress

        def progress(current_job: str, processed: int, total: int) -> None:
            original(current_job, processed, total)
            on_progress(processed, total)

        setattr(service.store, "progress", progress)
    service.process_job(job_id, user_id)
    return service.store.job(job_id, user_id)


class ImportTask(Task):  # type: ignore[misc]
    """Import task base used to keep the Celery class typed."""


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=ImportTask,
    name="src.tasks.imports.run_import_task",
    acks_late=True,
)
def run_import_task(self: ImportTask, job_id: str, user_id: str) -> dict[str, Any]:
    """Execute a pending import and copy progress plus the final status."""
    db = get_db_session()
    try:
        async_task = owned_async_task(db, "import", job_id, user_id)
        manager = TaskManager(db)
        manager.update_task_status(async_task.id, "running")

        def on_progress(processed: int, total: int) -> None:
            row = db.get(type(async_task), async_task.id)
            if row is None:
                return
            row.progress = {
                "current": processed,
                "total": total,
                "percentage": (processed / total * 100) if total else 0,
                "message": f"Imported {processed}/{total}",
            }
            db.commit()

        try:
            job = execute_import(job_id, user_id, on_progress)
        except ValueError as exc:
            manager.update_task_status(async_task.id, "failed", error_message=str(exc))
            raise

        status = str(job.get("status") or "failed")
        if status == "completed":
            manager.update_task_status(async_task.id, "completed")
        else:
            raw_result = job.get("result")
            detail = raw_result.get("detail") if isinstance(raw_result, dict) else None
            message = str(detail or "Import failed")
            manager.update_task_status(async_task.id, "failed", error_message=message)
        return {"job_id": job_id, "status": status}
    finally:
        db.close()
