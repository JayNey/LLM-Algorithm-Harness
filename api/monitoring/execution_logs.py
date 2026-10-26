"""Best-effort retained events from trusted, persisted async task records."""

import logging
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import SecretStr

from api.auth.config import AuthSettings
from api.auth.service import AuthService
from api.db.models import AsyncTask
from api.monitoring.config import MonitorSettings
from api.monitoring.store import MonitorStore

logger = logging.getLogger(__name__)
_EVENTS = {
    "task.queued",
    "task.started",
    "task.progress",
    "task.completed",
    "task.failed",
    "task.paused",
    "task.cancelled",
    "task.resumed",
    "unit.started",
    "unit.completed",
    "unit.failed",
}
_TEXT_FIELDS = {"problem_id", "strategy"}


def _event_data(data: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in _TEXT_FIELDS:
        value = data.get(name)
        if isinstance(value, str):
            result[name] = value
    for name in ("current", "total"):
        value = data.get(name)
        if type(value) is int and 0 <= value <= 2**63 - 1:
            result[name] = value
    value = data.get("percentage")
    if (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0 <= value <= 100
    ):
        result["percentage"] = value
    if data.get("status") in ("running", "completed", "failed", "cancelled", "paused"):
        result["status"] = data["status"]
    return result


def task_log_key(task_id: str) -> str:
    """Separate worker events from legacy run IDs, even when their UUIDs collide."""
    return "async:" + task_id


def record_execution_event(task: AsyncTask, event: str, data: dict[str, Any] | None = None) -> None:
    """Never accept HTTP owner claims, arbitrary messages, or raw exception bodies.

    The caller supplies a row loaded from its business session, after commit.
    Auth and monitoring connections are independent of that transaction. Cache
    keys include process and settings so prefork workers and separate apps do
    not reuse the wrong sink. No Redis subscriber is needed for persistence.
    """
    try:
        if event not in _EVENTS or task.task_type not in {
            "evaluation",
            "experiment",
            "benchmark",
            "import",
            "ab_test",
        }:
            return
        settings = AuthSettings()
        limits = MonitorSettings()
        auth, store = _configured_writer(
            os.getpid(),
            str(settings.AUTH_DATABASE_PATH.resolve()),
            settings.SECRET_KEY.get_secret_value(),
            settings.ENCRYPTION_KEY.get_secret_value(),
            limits.MONITOR_RETENTION_SECONDS,
            limits.MONITOR_MAX_ROWS,
        )
        secrets = [
            settings.SECRET_KEY.get_secret_value(),
            settings.ENCRYPTION_KEY.get_secret_value(),
        ]
        for key in auth.store.keys(task.user_id):
            # Fail closed if a saved key cannot be decrypted: omit this event
            # rather than persisting a value we cannot safely redact.
            secrets.append(
                auth.llm_config(key["id"], task.user_id, "log-redaction").api_key.get_secret_value()
            )
        context = _event_data(data or {})
        context.update(source="async_task_execution", kind=event, task_type=task.task_type)
        store.append_log(
            "ERROR" if event in {"task.failed", "unit.failed"} else "INFO",
            event,
            user_id=task.user_id,
            run_id=task_log_key(task.id),
            context=context,
            known_secrets=secrets,
        )
    except Exception:
        logger.warning("execution_log_write_failed")


@lru_cache(maxsize=4)
def _configured_writer(
    pid: int, path: str, secret: str, encryption: str, retention: int, rows: int
) -> tuple[AuthService, MonitorStore]:
    auth = AuthService(
        AuthSettings(
            _env_file=None,
            AUTH_DATABASE_PATH=Path(path),
            SECRET_KEY=SecretStr(secret),
            ENCRYPTION_KEY=SecretStr(encryption),
        )
    )
    return auth, MonitorStore(auth.store, retention, rows)
