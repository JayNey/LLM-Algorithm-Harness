"""Celery entry point for persisted A/B prompt tests."""

import logging
import uuid
from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from billiard.einfo import ExceptionWithTraceback
from billiard.exceptions import WorkerLostError
from celery import Task
from celery.signals import task_failure
from celery.worker.request import Request
from sqlalchemy import CursorResult, Engine, and_, or_, update

from api.db.models import AsyncTask
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.tasks.support import get_db_session

logger = logging.getLogger(__name__)


class ABTestRequest(Request):  # type: ignore[misc]
    """Carry a unique delivery attempt through the pool and its failure callback."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._request_dict["ab_execution_attempt"] = str(uuid.uuid4())

    def on_failure(
        self,
        exc_info: Any,
        send_failed_event: bool = True,
        return_ok: bool = False,
    ) -> None:
        error = exc_info.exception
        if isinstance(error, ExceptionWithTraceback):
            error = error.exc
        if isinstance(error, WorkerLostError):
            record_ab_test_failure(
                sender=self.task,
                task_id=self.id,
                args=self.args,
                kwargs=self.kwargs,
                exception=error,
                execution_attempt=self._request_dict["ab_execution_attempt"],
            )
        super().on_failure(exc_info, send_failed_event=send_failed_event, return_ok=return_ok)


class ABTestTask(Task):  # type: ignore[misc]
    """Typed bound A/B worker task."""

    Request = "src.tasks.ab_test:ABTestRequest"


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=ABTestTask,
    name="src.tasks.ab_test.run_ab_test_task",
    acks_late=True,
    reject_on_worker_lost=False,
)
def run_ab_test_task(self: ABTestTask, test_id: str, user_id: str) -> dict[str, Any]:
    """Resolve credentials in the worker and execute a single persisted task."""
    from api.services.ab_test_service import ABTestService

    service = ABTestService(recover=False)
    try:
        return service._execute(
            test_id,
            user_id,
            celery_task_id=self.request.id,
            execution_attempt=self.request.get("ab_execution_attempt"),
        )
    finally:
        service._engine.dispose()


@task_failure.connect(weak=False)  # type: ignore[untyped-decorator]
def record_ab_test_failure(
    sender: Any = None,
    task_id: str | None = None,
    args: Sequence[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    exception: BaseException | None = None,
    execution_attempt: str | None = None,
    **extra: Any,
) -> None:
    """Persist failures emitted by Celery, including loss of a child worker.

    With reject_on_worker_lost=False, Celery's parent records WorkerLostError
    and emits this signal instead of requeueing an already claimed execution.
    Ordinary broker redelivery is still handled by the atomic claim.
    """
    if getattr(sender, "name", None) != "src.tasks.ab_test.run_ab_test_task" or not task_id:
        return
    values = kwargs or {}
    test_id = args[0] if args else values.get("test_id")
    user_id = args[1] if args and len(args) > 1 else values.get("user_id")
    if not isinstance(test_id, str) or not isinstance(user_id, str):
        return
    db = None
    engine = None
    try:
        db = get_db_session()
        engine = db.get_bind()
        # A failed duplicate child must not stop the delivery holding the claim.
        eligible = AsyncTask.status == "pending"
        if isinstance(exception, WorkerLostError) and execution_attempt:
            eligible = or_(
                eligible,
                and_(
                    AsyncTask.status == "running",
                    AsyncTask.progress["execution_attempt"].as_string() == execution_attempt,
                ),
            )
        changed = db.execute(
            update(AsyncTask)
            .where(
                AsyncTask.task_type == "ab_test",
                AsyncTask.entity_id == test_id,
                AsyncTask.user_id == user_id,
                AsyncTask.celery_task_id == task_id,
                eligible,
            )
            .values(status="failed", completed_at=datetime.utcnow(), error_message=str(exception))
        )
        if cast(CursorResult[Any], changed).rowcount:
            task = db.query(AsyncTask).filter(AsyncTask.celery_task_id == task_id).one()
            TaskManager(db).update_task_status(task.id, "failed", error_message=str(exception))
        else:
            db.rollback()
    except Exception:
        logger.warning("ab_test_failure_persistence_unavailable")
    finally:
        if db is not None:
            db.close()
        if isinstance(engine, Engine):
            engine.dispose()
