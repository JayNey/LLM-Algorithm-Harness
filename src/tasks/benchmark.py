"""Celery task that runs one persisted benchmark run."""

from __future__ import annotations

from typing import Any

from celery import Task
from sqlalchemy.orm import Session

from api.db.models import AsyncTask, BenchmarkRun, utcnow
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session, owned_async_task


def execute_benchmark(run_id: str, user_id: str) -> None:
    """Run a pending benchmark. The service records accuracy, cost and status."""
    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from api.services.benchmark_service import BenchmarkService

    service = BenchmarkService(auth=AuthService(AuthSettings()), recover=False)
    try:
        service._execute(run_id, user_id)
    finally:
        service._engine.dispose()


def _is_paused(db: Session, task_id: str) -> bool:
    current = db.query(AsyncTask).populate_existing().filter(AsyncTask.id == task_id).first()
    return current is not None and current.status == "paused"


def _keep_paused(db: Session, run_id: str) -> None:
    run = db.get(BenchmarkRun, run_id)
    if run is not None and run.status == "running":
        run.status = "paused"
        run.updated_at = utcnow()
        db.commit()


class BenchmarkTask(Task):  # type: ignore[misc]
    """Benchmark task base used to keep the Celery class typed."""


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=BenchmarkTask,
    name="src.tasks.benchmark.run_benchmark_task",
    acks_late=True,
)
def run_benchmark_task(self: BenchmarkTask, run_id: str, user_id: str) -> dict[str, Any]:
    """Execute a pending benchmark run and mirror its terminal status."""
    db = get_db_session()
    claimed = False
    manager = TaskManager(db, celery_task_id=self.request.id)
    try:
        async_task = owned_async_task(db, "benchmark", run_id, user_id)
        manager._lock_business_task(async_task)
        if async_task.status != "pending" or (
            self.request.id and async_task.celery_task_id != self.request.id
        ):
            return {"run_id": run_id, "status": async_task.status}
        run = db.get(BenchmarkRun, run_id)
        if run is None or run.user_id != user_id:
            message = f"Benchmark run {run_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        if run.status != "pending":
            message = f"Cannot start benchmark run in {run.status} status"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)

        claimed = manager.claim_task(async_task.id, self.request.id)
        if not claimed:
            return {"run_id": run_id, "status": async_task.status}
        try:
            execute_benchmark(run_id, user_id)
        except Exception as exc:
            db.rollback()
            if _is_paused(db, async_task.id):
                _keep_paused(db, run_id)
                return {"run_id": run_id, "status": "paused"}
            run = db.get(BenchmarkRun, run_id)
            if run is not None and run.status not in ("completed", "failed", "cancelled", "paused"):
                run.status = "failed"
                run.error_message = str(exc)
                db.commit()
            manager.update_task_status(async_task.id, "failed", error_message=str(exc))
            raise

        db.expire_all()
        run = db.get(BenchmarkRun, run_id)
        current_task = db.get(AsyncTask, async_task.id)
        if run is None or current_task is None:
            raise ValueError(f"Benchmark run {run_id} not found")
        if run.status == "cancelled" or current_task.status == "cancelled":
            if current_task.status != "cancelled":
                manager.update_task_status(current_task.id, "cancelled")
            return {"run_id": run_id, "status": "cancelled"}
        if _is_paused(db, async_task.id) or run.status == "paused":
            _keep_paused(db, run_id)
            return {"run_id": run_id, "status": "paused"}
        if run.status == "completed":
            manager.update_task_status(async_task.id, "completed")
            return {
                "run_id": run_id,
                "status": "completed",
                "accuracy": run.accuracy,
                "cost_usd": run.cost_usd,
            }
        message = run.error_message or "Benchmark failed"
        manager.update_task_status(async_task.id, "failed", error_message=message)
        return {"run_id": run_id, "status": "failed"}
    finally:
        if claimed:
            manager.confirm_stopped(async_task.id)
        db.close()
