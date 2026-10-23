"""Authenticate and bound file transfers before parsing or reading artifacts."""

import asyncio
import time

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.auth.cookies import ACCESS_COOKIE
from api.auth.service import unauthorized
from api.middleware.errors import ApiError, error_response

UPLOAD_PATHS = {"/api/v1/files/upload", "/api/v1/problems/upload", "/api/v1/configs/upload"}


class UploadBoundaryMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"].rstrip("/")
        is_upload = scope["method"] == "POST" and path in UPLOAD_PATHS
        is_download = scope["method"] == "GET" and (
            path == "/api/v1/problems/export"
            or path.startswith("/api/v1/files/")
            and path.endswith("/download")
            or path.startswith("/api/v1/results/")
        )
        if not is_upload and not is_download:
            await self.app(scope, receive, send)
            return
        service = scope["app"].state.files
        headers = dict(scope.get("headers", []))
        connection = HTTPConnection(scope)

        def check_identity() -> None:
            # Match current_user: an explicit header always wins over cookies,
            # including an empty, malformed or expired Authorization value.
            header = connection.headers.get("authorization")
            if header is not None:
                parts = header.split()
                if len(parts) != 2 or parts[0].lower() != "bearer":
                    raise unauthorized()
                token = parts[1]
            else:
                token = connection.cookies.get(ACCESS_COOKIE)
                if token is None:
                    raise unauthorized()
            principal = service.auth.authenticate(token)
            if is_upload:
                ip = scope["client"][0] if scope.get("client") else "unknown"
                service.auth.limit("upload-ip:" + ip, service.settings.FILE_UPLOAD_RATE_LIMIT)
                service.auth.limit(
                    "upload-user:" + principal.user_id, service.settings.FILE_UPLOAD_RATE_LIMIT
                )

        try:
            await run_in_threadpool(check_identity)
        except HTTPException as error:
            await error_response(
                scope,
                error.status_code,
                error.detail,
                code=error.error_code if isinstance(error, ApiError) else None,
                details=error.details if isinstance(error, ApiError) else None,
                headers={**(error.headers or {}), "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        if not service.transfers.acquire(blocking=False):
            await error_response(
                scope,
                429,
                "File transfer capacity reached",
                headers={"Retry-After": "1", "Cache-Control": "no-store"},
            )(scope, receive, send)
            return
        try:
            if is_download:
                await self.app(scope, receive, send)
                return
            maximum = service.settings.FILE_UPLOAD_MAX_BYTES
            if path == "/api/v1/configs/upload":
                maximum = min(maximum, service.settings.FILE_CONFIG_MAX_BYTES)
            maximum += 65536
            if b"content-length" in headers:
                try:
                    length = int(headers[b"content-length"])
                    if length < 0:
                        raise ValueError
                except ValueError:
                    await error_response(scope, 400, "Invalid content length")(scope, receive, send)
                    return
                if length > maximum:
                    await error_response(
                        scope,
                        413,
                        "Maximum upload size exceeded",
                        headers={"Cache-Control": "no-store"},
                    )(scope, receive, send)
                    return
            consumed, rejection = 0, 0
            started = time.monotonic()

            async def bounded_receive() -> Message:
                nonlocal consumed, rejection
                remaining = service.settings.FILE_UPLOAD_TIMEOUT_SECONDS - (
                    time.monotonic() - started
                )
                try:
                    if remaining <= 0:
                        raise asyncio.TimeoutError
                    message = await asyncio.wait_for(
                        receive(), timeout=min(remaining, service.settings.FILE_UPLOAD_IDLE_SECONDS)
                    )
                except asyncio.TimeoutError:
                    rejection = 408
                    raise MultiPartException("Upload timed out") from None
                if message["type"] == "http.disconnect":
                    raise MultiPartException("Upload interrupted")
                consumed += len(message.get("body", b""))
                if consumed > maximum:
                    rejection = 413
                    # Parser cleanup catches this exact exception type.
                    raise MultiPartException("Maximum upload size exceeded")
                return message

            async def bounded_send(message: Message) -> None:
                if not rejection:
                    await send(message)

            await self.app(scope, bounded_receive, bounded_send)
            if rejection:
                detail = "Upload timed out" if rejection == 408 else "Maximum upload size exceeded"
                await error_response(
                    scope, rejection, detail, headers={"Cache-Control": "no-store"}
                )(scope, receive, send)
        finally:
            service.transfers.release()
