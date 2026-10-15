"""Celery task that runs one persisted benchmark run."""

from __future__ import annotations

from typing import Any

from celery import Task

from api.db.models import AsyncTask, BenchmarkRun, utcnow
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session, owned_async_task


def execute_benchmark(run_id: str, user_id: str) -> None:
    """Run a pending benchmark. The service records accuracy, cost and status."""
    from api.services.benchmark_service import BenchmarkService

    BenchmarkService(recover=False)._execute(run_id, user_id)


def _is_paused(db, task_id: str) -> bool:
    current = db.query(AsyncTask).populate_existing().filter(AsyncTask.id == task_id).first()
    return current is not None and current.status == "paused"


def _keep_paused(db, run_id: str) -> None:
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
    try:
        async_task = owned_async_task(db, "benchmark", run_id, user_id)
        manager = TaskManager(db)
        run = db.get(BenchmarkRun, run_id)
        if run is None or run.user_id != user_id:
            message = f"Benchmark run {run_id} not found"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)
        if run.status != "pending":
            message = f"Cannot start benchmark run in {run.status} status"
            manager.update_task_status(async_task.id, "failed", error_message=message)
            raise ValueError(message)

        manager.update_task_status(async_task.id, "running")
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
        db.close()
