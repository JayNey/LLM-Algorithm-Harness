"""Reusable identity dependency for evaluations, files and WebSocket consumers."""

from typing import Literal, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.auth.cookies import ACCESS_COOKIE
from api.auth.service import AuthService, Principal, unauthorized
from api.monitoring.config import MonitorSettings

UserRole = Literal["user", "admin"]

bearer = HTTPBearer(auto_error=False)


def auth_service(request: Request) -> AuthService:
    return cast(AuthService, request.app.state.auth)


def current_user(
    request: Request,
    service: AuthService = Depends(auth_service),
    credential: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    header = request.headers.get("authorization")
    token: str
    if header is not None:
        if credential is None or credential.scheme.lower() != "bearer":
            raise unauthorized()
        token = credential.credentials
    else:
        cookie = request.cookies.get(ACCESS_COOKIE)
        if cookie is None:
            raise unauthorized()
        token = cookie
    principal = service.authenticate(token)
    request.state.monitor_user_id = principal.user_id
    service.limit("protected:" + principal.user_id, service.settings.AUTH_PROTECTED_RATE_LIMIT)
    return principal


def current_role(request: Request, principal: Principal = Depends(current_user)) -> UserRole:
    """Resolve roles from operator configuration, never client or token claims."""
    settings = cast(MonitorSettings, request.app.state.monitor.settings)
    return "admin" if settings.is_admin(principal.user_id) else "user"


def auth_attempt(request: Request, service: AuthService = Depends(auth_service)) -> None:
    # Do not trust user-controlled X-Forwarded-For. Trusted proxies must be
    # explicitly configured at the ASGI server boundary.
    ip = request.client.host if request.client else "unknown"
    service.limit("auth:" + ip)
