"""Retry publication from committed database snapshots without running the model."""

from __future__ import annotations

from typing import Any

from celery import Task
from fastapi import HTTPException

from src.celery_app import celery_app
from src.tasks.evaluation import get_artifact_service
from src.tasks.support import get_db_session


@celery_app.task(bind=True, name="src.tasks.artifacts.publish_evaluation_artifacts", max_retries=3, acks_late=True)  # type: ignore[untyped-decorator]
def publish_evaluation_artifacts(
    self: Task, evaluation_id: str, owner: str, revision: int, manual: bool = False
) -> dict[str, Any]:
    db = get_db_session()
    try:
        try:
            state = get_artifact_service(db).publish(evaluation_id, owner, revision, manual)
        except HTTPException as exc:
            if exc.status_code == 404:
                return {
                    "status": "unavailable",
                    "available": False,
                    "error_code": "result_not_found",
                }
            raise
        if (
            state["revision"] == revision
            and state["status"] == "failed"
            and state["error_code"] == "storage_error"
        ):
            raise self.retry(countdown=min(10 * 2**self.request.retries, 300))
        return state
    finally:
        db.close()
