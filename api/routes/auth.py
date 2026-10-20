"""Public auth endpoints and protected profile/provider credential endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from api.auth.cookies import (
    PERSIST_COOKIE,
    REFRESH_COOKIE,
    clear_auth_cookies,
    set_auth_cookies,
)
from api.auth.dependencies import UserRole, auth_attempt, auth_service, current_role, current_user
from api.auth.models import (
    KeyCreate,
    KeyUpdate,
    LoginInput,
    PasswordChange,
    ProfileUpdate,
    RefreshInput,
    RegisterInput,
)
from api.auth.service import AuthService, Principal, unauthorized
from api.schemas import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["authentication"])


@router.post("/auth/register", status_code=201, dependencies=[Depends(auth_attempt)])
def register(
    request: RegisterInput, service: AuthService = Depends(auth_service)
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(success=True, data=service.register(request), message="User registered")


def _secure(request: Request) -> bool:
    return request.url.scheme == "https"


def _issue(
    request: Request,
    response: Response,
    service: AuthService,
    tokens: dict[str, Any],
    *,
    persistent: bool,
    message: str,
) -> ApiResponse[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    if (
        isinstance(tokens.get("expires_in"), int)
        and isinstance(tokens.get("access_token"), str)
        and isinstance(tokens.get("refresh_token"), str)
    ):
        set_auth_cookies(
            response,
            tokens,
            persistent=persistent,
            secure=_secure(request),
            refresh_max_age=service.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        )
    return ApiResponse(success=True, data=tokens, message=message)


@router.post("/auth/login", dependencies=[Depends(auth_attempt)])
def login(
    body: LoginInput,
    request: Request,
    response: Response,
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    tokens = service.login(body.username, body.password.get_secret_value())
    return _issue(
        request, response, service, tokens, persistent=body.remember, message="Authenticated"
    )


@router.post("/auth/refresh", dependencies=[Depends(auth_attempt)])
def refresh(
    body: RefreshInput,
    request: Request,
    response: Response,
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    supplied = body.refresh_token.get_secret_value() if body.refresh_token else None
    token = supplied or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise unauthorized()
    tokens = service.refresh(token)
    return _issue(
        request,
        response,
        service,
        tokens,
        persistent=request.cookies.get(PERSIST_COOKIE) == "1",
        message="Tokens refreshed",
    )


@router.post("/auth/logout", status_code=204)
def logout(
    request: Request,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> Response:
    service.logout(principal)
    response = Response(status_code=204)
    clear_auth_cookies(response, secure=_secure(request))
    return response


@router.get("/users/me")
def me(
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
    role: UserRole = Depends(current_role),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True,
        data={**service.public_user(principal.user_id), "role": role},
        message="Current user",
    )


@router.post("/users/me/password", status_code=204)
def change_password(
    request: PasswordChange,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> Response:
    service.change_password(principal, request)
    return Response(status_code=204)


@router.patch("/users/me")
def update_me(
    request: ProfileUpdate,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True, data=service.update_user(principal, request), message="Profile updated"
    )


@router.get("/api-keys")
def list_keys(
    principal: Principal = Depends(current_user), service: AuthService = Depends(auth_service)
) -> ApiResponse[list[dict[str, Any]]]:
    return ApiResponse(
        success=True,
        data=[service.key_metadata(k) for k in service.store.keys(principal.user_id)],
        message="API keys",
    )


@router.post("/api-keys", status_code=201)
def add_key(
    request: KeyCreate,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True, data=service.add_key(principal.user_id, request), message="API key stored"
    )


@router.patch("/api-keys/{key_id}")
def update_key(
    key_id: str,
    request: KeyUpdate,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True,
        data=service.update_key(key_id, principal.user_id, request),
        message="API key updated",
    )


@router.delete("/api-keys/{key_id}", status_code=204)
def delete_key(
    key_id: str,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> Response:
    service.delete_key(key_id, principal.user_id)
    return Response(status_code=204)


@router.post("/api-keys/{key_id}/verify")
def verify_key(
    key_id: str,
    principal: Principal = Depends(current_user),
    service: AuthService = Depends(auth_service),
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True,
        data=service.verify_key(key_id, principal.user_id),
        message="Connection check completed",
    )
