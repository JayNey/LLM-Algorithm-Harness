"""ASGI request logging without request-body or Authorization inspection.

Using a direct ASGI wrapper preserves multipart receive exceptions so the
parser can close spool files when an upload exceeds its byte limit.
"""

import logging
import time

from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.middleware.errors import request_id

logger = logging.getLogger(__name__)


class LoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        identity = request_id(scope)
        start_time = time.monotonic()
        status_code: int | None = None
        response_elapsed_ms: float | None = None

        async def logged_send(message: Message) -> None:
            nonlocal status_code, response_elapsed_ms
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [
                    (key, value)
                    for key, value in message.get("headers", [])
                    if key.lower() != b"x-request-id"
                ]
                message = {
                    **message,
                    "headers": [*headers, (b"x-request-id", identity.encode("ascii"))],
                }
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                response_elapsed_ms = (time.monotonic() - start_time) * 1000

        try:
            await self.app(scope, receive, logged_send)
        except Exception:
            if status_code is None:
                # The outer ASGI server error handler emits the final 500.
                status_code = 500
            raise
        finally:
            elapsed_ms = (
                response_elapsed_ms
                if response_elapsed_ms is not None
                else (time.monotonic() - start_time) * 1000
            )
            route = getattr(scope.get("route"), "path", "[unmatched]")
            if not isinstance(route, str):
                route = "[unmatched]"
            logger.info(
                "Request completed: %s %s %s request_id=%s",
                scope["method"],
                route,
                status_code,
                identity,
            )
            app = scope.get("app")
            monitor = getattr(getattr(app, "state", None), "monitor", None)
            store = getattr(monitor, "store", None)
            if store is not None and status_code is not None:
                try:
                    await run_in_threadpool(
                        store.record_request,
                        scope["method"],
                        route,
                        status_code,
                        elapsed_ms,
                        scope.get("state", {}).get("monitor_user_id"),
                    )
                except Exception:
                    # Monitoring cannot replace the original response/exception.
                    logger.warning("monitor_request_write_failed")
                    mark_gap = getattr(store, "mark_capture_gap", None)
                    if callable(mark_gap):
                        try:
                            await run_in_threadpool(mark_gap)
                        except Exception:
                            logger.warning("monitor_capture_gap_write_failed")


def setup_logging_middleware(app: FastAPI) -> FastAPI:
    app.add_middleware(LoggingMiddleware)
    return app
