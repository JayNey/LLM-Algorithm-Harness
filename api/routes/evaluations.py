"""Authenticated evaluation endpoints with owner-scoped service operations."""

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth.dependencies import auth_service, current_user
from api.auth.service import AuthService, Principal
from api.files.dependencies import file_service
from api.files.service import FileService
from api.models import EvaluationCreateRequest, EvaluationUpdateRequest
from api.schemas import ApiResponse, EvaluationResponse, PaginatedData, ProgressInfo
from api.services import EvaluationService

router = APIRouter(prefix="/api/v1", tags=["evaluations"])
T = TypeVar("T")


def evaluation_service(request: Request) -> EvaluationService:
    return request.app.state.evaluations


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        # Service errors contain task state/IDs only, never provider credentials.
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


@router.post("/evaluations", status_code=201)
def create_evaluation(
    request: EvaluationCreateRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: EvaluationService = Depends(evaluation_service),
    files: FileService = Depends(file_service),
) -> ApiResponse[EvaluationResponse]:
    auth.owned_key(request.api_key_id, principal.user_id)
    result = service.create_evaluation(request, principal.user_id)
    try:
        files.store.register_run(result.evaluation_id, principal.user_id)
    except Exception:
        service.delete_evaluation(result.evaluation_id, principal.user_id)
        raise
    auth.audit("evaluation_create", principal.user_id, result.evaluation_id)
    return ApiResponse(success=True, data=result, message="Evaluation created successfully")


@router.get("/evaluations")
def list_evaluations(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[PaginatedData[EvaluationResponse]]:
    limit = limit if 1 <= limit <= 100 else 20
    offset = max(0, offset)
    results, total = service.list_evaluations(
        principal.user_id, status=status, limit=limit, offset=offset
    )
    data = PaginatedData(
        items=results, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Evaluations retrieved successfully")


@router.get("/evaluations/{evaluation_id}")
def get_evaluation(
    evaluation_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[EvaluationResponse]:
    result = call(lambda: service.get_evaluation(evaluation_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Evaluation retrieved successfully")


@router.patch("/evaluations/{evaluation_id}")
def update_evaluation(
    evaluation_id: str,
    request: EvaluationUpdateRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[EvaluationResponse]:
    result = call(lambda: service.update_evaluation(evaluation_id, request, principal.user_id))
    auth.audit("evaluation_update", principal.user_id, evaluation_id)
    return ApiResponse(success=True, data=result, message="Evaluation updated successfully")


@router.delete("/evaluations/{evaluation_id}", status_code=204)
def delete_evaluation(
    evaluation_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: EvaluationService = Depends(evaluation_service),
    files: FileService = Depends(file_service),
) -> None:
    call(
        lambda: service.delete_evaluation(
            evaluation_id,
            principal.user_id,
            lambda: files.delete_run(evaluation_id, principal.user_id),
        )
    )
    auth.audit("evaluation_delete", principal.user_id, evaluation_id)


@router.post("/evaluations/{evaluation_id}/start", status_code=202)
def start_evaluation(
    evaluation_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[EvaluationResponse]:
    key_id = call(lambda: service.credential_id(evaluation_id, principal.user_id))
    auth.owned_key(key_id, principal.user_id)
    result = call(lambda: service.start_evaluation(evaluation_id, principal.user_id))
    auth.audit("evaluation_start", principal.user_id, evaluation_id)
    return ApiResponse(success=True, data=result, message="Evaluation started successfully")


@router.get("/evaluations/{evaluation_id}/progress")
def get_evaluation_progress(
    evaluation_id: str,
    principal: Principal = Depends(current_user),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[ProgressInfo]:
    progress = call(lambda: service.get_progress(evaluation_id, principal.user_id))
    return ApiResponse(success=True, data=progress, message="Progress retrieved successfully")


@router.post("/evaluations/{evaluation_id}/cancel")
def cancel_evaluation(
    evaluation_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: EvaluationService = Depends(evaluation_service),
) -> ApiResponse[EvaluationResponse]:
    result = call(lambda: service.cancel_evaluation(evaluation_id, principal.user_id))
    auth.audit("evaluation_cancel", principal.user_id, evaluation_id)
    return ApiResponse(success=True, data=result, message="Evaluation cancelled successfully")
