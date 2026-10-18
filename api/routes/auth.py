"""Public auth endpoints and protected profile/provider credential endpoints."""

from typing import Any

from fastapi import APIRouter, Depends, Response

from api.auth.dependencies import auth_attempt, auth_service, current_user
from api.auth.models import (
    KeyCreate,
    KeyUpdate,
    LoginInput,
    PasswordChange,
    ProfileUpdate,
    RefreshInput,
    RegisterInput,
)
from api.auth.service import AuthService, Principal
from api.schemas import ApiResponse

router = APIRouter(prefix="/api/v1", tags=["authentication"])


@router.post("/auth/register", status_code=201, dependencies=[Depends(auth_attempt)])
def register(
    request: RegisterInput, service: AuthService = Depends(auth_service)
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(success=True, data=service.register(request), message="User registered")


@router.post("/auth/login", dependencies=[Depends(auth_attempt)])
def login(
    request: LoginInput, response: Response, service: AuthService = Depends(auth_service)
) -> ApiResponse[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(
        success=True,
        data=service.login(request.username, request.password.get_secret_value()),
        message="Authenticated",
    )


@router.post("/auth/refresh", dependencies=[Depends(auth_attempt)])
def refresh(
    request: RefreshInput, response: Response, service: AuthService = Depends(auth_service)
) -> ApiResponse[dict[str, Any]]:
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(
        success=True,
        data=service.refresh(request.refresh_token.get_secret_value()),
        message="Tokens refreshed",
    )


@router.post("/auth/logout", status_code=204)
def logout(
    principal: Principal = Depends(current_user), service: AuthService = Depends(auth_service)
) -> Response:
    service.logout(principal)
    return Response(status_code=204)


@router.get("/users/me")
def me(
    principal: Principal = Depends(current_user), service: AuthService = Depends(auth_service)
) -> ApiResponse[dict[str, Any]]:
    return ApiResponse(
        success=True, data=service.public_user(principal.user_id), message="Current user"
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
