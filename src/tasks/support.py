"""Shared helpers for Celery tasks that mirror status onto async_tasks."""

from __future__ import annotations

from sqlalchemy.orm import Session

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask


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
