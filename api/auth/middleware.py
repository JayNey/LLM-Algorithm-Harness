"""Bound auth request bodies before parsing and avoid caching private responses."""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.middleware.errors import error_response


class AuthBoundaryMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return

        async def private_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [
                    (k, v) for k, v in message.get("headers", []) if k.lower() != b"cache-control"
                ]
                message = {**message, "headers": [*headers, (b"cache-control", b"no-store")]}
            await send(message)

        path = scope["path"]
        sensitive_input = any(
            path.startswith(prefix)
            for prefix in (
                "/api/v1/auth/",
                "/api/v1/api-keys",
                "/api/v1/users/",
                "/api/v1/problems/import",
            )
        )
        if sensitive_input and scope["method"] in {"POST", "PATCH", "PUT"}:
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > 16384:
                    response = error_response(scope, 413, "Request body too large")
                    await response(scope, receive, private_send)
                    return
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            sent = False

            async def replay() -> Message:
                nonlocal sent
                if not sent:
                    sent = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, replay, private_send)
        else:
            await self.app(scope, receive, private_send)
