"""Double-submit CSRF for cookie-authenticated mutations."""

import hmac
import json
from typing import Any

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import HTTPConnection
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.auth.cookies import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    CSRF_PATH,
    PERSIST_COOKIE,
    REFRESH_COOKIE,
    new_csrf_token,
)
from api.middleware.errors import ErrorCode, error_response

CSRF_HEADER = "x-csrf-token"
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def csrf_matches(expected: str | None, provided: str | None) -> bool:
    if not expected or not provided or len(expected) != len(provided):
        return False
    return hmac.compare_digest(expected, provided)


def request_cookies(scope: Scope) -> dict[str, str]:
    return dict(HTTPConnection(scope).cookies)


def cookie_authenticated(scope: Scope) -> bool:
    headers = Headers(scope=scope)
    if headers.get("authorization") is not None:
        return False
    cookies = request_cookies(scope)
    return ACCESS_COOKIE in cookies or REFRESH_COOKIE in cookies


def cookie_pair_value(header: str, name: str) -> str | None:
    key, separator, value = header.split(";", 1)[0].partition("=")
    if separator != "=" or key.strip() != name:
        return None
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def csrf_set_cookie(token: str, *, secure: bool, max_age: int | None) -> bytes:
    response = Response()
    response.set_cookie(
        CSRF_COOKIE,
        token,
        max_age=max_age,
        httponly=False,
        secure=secure,
        samesite="lax",
        path=CSRF_PATH,
    )
    for key, value in response.headers.raw:
        if key.lower() == b"set-cookie":
            return value
    raise RuntimeError("CSRF cookie header was not produced")


def persist_max_age(scope: Scope) -> int | None:
    if request_cookies(scope).get(PERSIST_COOKIE) != "1":
        return None
    app: Any = scope.get("app")
    auth = getattr(getattr(app, "state", None), "auth", None)
    settings = getattr(auth, "settings", None)
    days = getattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", None)
    if not isinstance(days, int):
        return None
    return days * 86400


def publish_csrf(scope: Scope, message: Message) -> Message:
    headers = MutableHeaders(raw=list(message.get("headers", [])))
    issued: str | None = None
    cleared = False
    for value in headers.getlist("set-cookie"):
        parsed = cookie_pair_value(value, CSRF_COOKIE)
        if parsed is None:
            continue
        if parsed == "":
            cleared = True
        else:
            issued = parsed
    token = issued
    if token is None and not cleared:
        token = request_cookies(scope).get(CSRF_COOKIE)
    status = int(message.get("status", 200))
    if (
        token is None
        and not cleared
        and status < 400
        and (ACCESS_COOKIE in request_cookies(scope) or REFRESH_COOKIE in request_cookies(scope))
    ):
        token = new_csrf_token()
        headers.append(
            "set-cookie",
            csrf_set_cookie(
                token,
                secure=scope.get("scheme") == "https",
                max_age=persist_max_age(scope),
            ).decode("latin-1"),
        )
    if token is None:
        return {**message, "headers": headers.raw}
    if CSRF_HEADER in headers:
        del headers[CSRF_HEADER]
    headers[CSRF_HEADER] = token
    return {**message, "headers": headers.raw}


def skips_csrf(path: str) -> bool:
    """Login and registration do not consume the session cookie."""
    return path.endswith("/auth/login") or path.endswith("/auth/register")


async def explicit_refresh_token(receive: Receive) -> tuple[bool, Receive]:
    """JSON refresh_token wins over the refresh cookie, matching the auth route."""
    chunks: list[bytes] = []
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":

            async def disconnected() -> Message:
                return message

            return False, disconnected
        chunks.append(message.get("body", b""))
        if not message.get("more_body", False):
            break
    body = b"".join(chunks)
    supplied = False
    if 0 < len(body) <= 16384:
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        token = payload.get("refresh_token") if isinstance(payload, dict) else None
        supplied = isinstance(token, str) and len(token) > 0
    sent = False

    async def replay() -> Message:
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        return await receive()

    return supplied, replay


class CsrfMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not str(scope.get("path", "")).startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        method = str(scope.get("method", "GET")).upper()
        path = str(scope.get("path", ""))
        if method in UNSAFE_METHODS and cookie_authenticated(scope) and not skips_csrf(path):
            replay: Receive = receive
            supplied_refresh = False
            if path.endswith("/auth/refresh"):
                supplied_refresh, replay = await explicit_refresh_token(receive)
            headers = Headers(scope=scope)
            if not supplied_refresh and not csrf_matches(
                request_cookies(scope).get(CSRF_COOKIE), headers.get(CSRF_HEADER)
            ):
                response = error_response(scope, 403, "跨站请求被拒绝", code=ErrorCode.FORBIDDEN)
                await response(scope, receive, send)
                return
            receive = replay

        async def send_with_csrf(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = publish_csrf(scope, message)
            await send(message)

        await self.app(scope, receive, send_with_csrf)
