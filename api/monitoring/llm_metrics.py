"""Best-effort bridge from SDK attempts to the deployment's shared auth DB.

Only booleans and durations enter this sink. Client code isolates import,
configuration and persistence failures from provider responses and errors.
"""

import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from api.auth.config import AuthSettings
from api.auth.store import AuthStore
from api.monitoring.config import MonitorSettings
from api.monitoring.store import MonitorStore


class _CaptureAuthStore(AuthStore):
    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with super().connection() as db:
            # Applies during initialization too, before schema or prune writes.
            db.execute("PRAGMA busy_timeout=100")
            yield db


@lru_cache(maxsize=4)
def _configured_writer(pid: int, path: str, retention: int, rows: int) -> MonitorStore:
    # No open connections cross fork boundaries or are retained in the cache.
    return MonitorStore(_CaptureAuthStore(Path(path)), retention, rows)


def record_call(succeeded: bool, duration_ms: float) -> None:
    settings = AuthSettings()
    limits = MonitorSettings()
    writer = _configured_writer(
        os.getpid(),
        str(settings.AUTH_DATABASE_PATH.resolve()),
        limits.MONITOR_RETENTION_SECONDS,
        limits.MONITOR_MAX_ROWS,
    )
    writer.record_llm_call(succeeded, duration_ms)
