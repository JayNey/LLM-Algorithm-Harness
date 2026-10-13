"""Reusable identity dependency for evaluations, files and WebSocket consumers."""

from typing import cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth.service import AuthService, Principal, unauthorized

bearer = HTTPBearer(auto_error=False)


def auth_service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth)


def current_user(
    request: Request,
    service: AuthService = Depends(auth_service),
    credential: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if credential is None or credential.scheme.lower() != "bearer":
        raise unauthorized()
    principal = service.authenticate(credential.credentials)
    request.state.monitor_user_id = principal.user_id
    service.limit("protected:" + principal.user_id, service.settings.AUTH_PROTECTED_RATE_LIMIT)
    return principal


def auth_attempt(request: Request, service: AuthService = Depends(auth_service)) -> None:
    # Do not trust user-controlled X-Forwarded-For. Trusted proxies must be
    # explicitly configured at the ASGI server boundary.
    ip = request.client.host if request.client else "unknown"
    service.limit("auth:" + ip)
