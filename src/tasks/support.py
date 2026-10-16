"""Shared helpers for Celery tasks that mirror status onto async_tasks."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask


def progress_percentage(current: int, total: int) -> float:
    """Return a completion percentage clamped to [0, 100]."""
    if total <= 0:
        return 0.0
    return min(100.0, max(0.0, (current / total) * 100))


def task_progress(current: int, total: int, current_step: str) -> dict[str, Any]:
    """Progress JSON stored on an async task."""
    return {
        "current": current,
        "total": total,
        "percentage": progress_percentage(current, total),
        "current_step": current_step,
    }


def get_db_session() -> Session:
    """Open a business-database session for one task execution."""
    engine = make_engine(business_database_url())
    return make_session_factory(engine)()


def owned_async_task(db: Session, task_type: str, entity_id: str, user_id: str) -> AsyncTask:
    """Return the caller's async task row for a business entity."""
    task = (
        db.query(AsyncTask)
        .filter(
            AsyncTask.task_type == task_type,
            AsyncTask.entity_id == entity_id,
            AsyncTask.user_id == user_id,
        )
        .first()
    )
    if task is None:
        raise ValueError(f"{task_type} task for {entity_id} not found")
    return task
