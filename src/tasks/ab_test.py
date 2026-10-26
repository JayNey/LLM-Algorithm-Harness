"""Celery entry point for persisted A/B prompt tests."""

from typing import Any

from celery import Task

from src.celery_app import celery_app


class ABTestTask(Task):  # type: ignore[misc]
    """Typed bound A/B worker task."""


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=ABTestTask,
    name="src.tasks.ab_test.run_ab_test_task",
    acks_late=True,
)
def run_ab_test_task(self: ABTestTask, test_id: str, user_id: str) -> dict[str, Any]:
    """Resolve credentials in the worker and execute a single persisted task."""
    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from api.services.ab_test_service import ABTestService

    service = ABTestService(auth=AuthService(AuthSettings()), recover=False)
    try:
        return service._execute(test_id, user_id, celery_task_id=self.request.id)
    finally:
        service._engine.dispose()
