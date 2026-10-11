"""ASGI request logging without request-body or Authorization inspection.

Using a direct ASGI wrapper preserves multipart receive exceptions so the
parser can close spool files when an upload exceeds its byte limit.
"""

import logging
import time

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class LoggingMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start_time = time.monotonic()
        logger.info(
            "Incoming request: %s %s",
            scope["method"],
            scope["path"],
            extra={"method": scope["method"], "path": scope["path"]},
        )

        async def logged_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                logger.info(
                    "Response sent: %s",
                    message["status"],
                    extra={
                        "status_code": message["status"],
                        "process_time": time.monotonic() - start_time,
                    },
                )
            await send(message)

        await self.app(scope, receive, logged_send)


def setup_logging_middleware(app):
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    app.add_middleware(LoggingMiddleware)
    return app
