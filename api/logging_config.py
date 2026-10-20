"""API logging assembly driven by LOG_LEVEL / LOG_FORMAT (issue #159).

Reuses :func:`src.utils.logging.setup_logging` for structlog rendering and
routes the uvicorn loggers through the same handlers, so a deployment switches
between human-readable and JSON output purely via the environment.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_LOG_FORMATS = ("text", "json")


class JsonLineFormatter(logging.Formatter):
    """Root formatter for JSON mode.

    structlog events arrive at the root handler already rendered as a JSON
    object and pass through untouched; plain stdlib records (uvicorn access
    and error logs) are wrapped in a JSON object with the same key names
    structlog uses (timestamp/level/logger/event).
    """

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        try:
            parsed = json.loads(message)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return message
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "event": message,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_api_logging(
    *,
    enabled: bool | None = None,
    level: str | None = None,
    fmt: str | None = None,
) -> None:
    """Apply LOG_LEVEL and LOG_FORMAT to the process-wide logging setup.

    ``enabled`` defaults to False under pytest so test suites keep their
    capture handlers attached to the root logger; pass ``enabled=True`` in
    tests that exercise the real assembly.
    """
    if enabled is None:
        enabled = "pytest" not in sys.modules
    if not enabled:
        return

    from api.config import settings
    from src.utils.logging import setup_logging

    resolved_level = (level or settings.LOG_LEVEL).upper()
    resolved_fmt = (fmt or settings.LOG_FORMAT).lower()
    if resolved_fmt not in _LOG_FORMATS:
        raise ValueError(f"Unsupported LOG_FORMAT: {settings.LOG_FORMAT}")

    setup_logging(
        level=resolved_level,
        console_format="console" if resolved_fmt == "text" else "json",
    )

    root = logging.getLogger()
    if resolved_fmt == "json":
        for handler in root.handlers:
            if isinstance(handler, logging.StreamHandler) and not isinstance(
                handler, logging.FileHandler
            ):
                handler.setFormatter(JsonLineFormatter())
    else:
        for handler in root.handlers:
            if isinstance(handler.formatter, JsonLineFormatter):
                handler.setFormatter(logging.Formatter("%(message)s"))

    # uvicorn installs its own handlers before the app module is imported;
    # detach them so uvicorn lines follow LOG_FORMAT via the root handlers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv_logger = logging.getLogger(name)
        uv_logger.handlers.clear()
        uv_logger.propagate = True
