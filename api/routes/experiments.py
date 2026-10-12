"""Experiment management endpoints (issue #156)."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth.dependencies import auth_service, current_user
from api.auth.service import AuthService, Principal
from api.experiment_models import ExperimentCreateRequest
from api.schemas import ApiResponse, PaginatedData
from api.services import ExperimentService

router = APIRouter(prefix="/api/v1", tags=["experiments"])
T = TypeVar("T")


def experiment_service(request: Request) -> ExperimentService:
    return cast(ExperimentService, request.app.state.experiments)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


@router.post("/experiments", status_code=201)
def create_experiment(
    request: ExperimentCreateRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.create_experiment(request, principal.user_id))
    auth.audit("experiment_create", principal.user_id, result["id"])
    return ApiResponse(success=True, data=result, message="Experiment created successfully")


@router.get("/experiments")
def list_experiments(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit = limit if 1 <= limit <= 100 else 20
    offset = max(0, offset)
    results, total = service.list_experiments(
        principal.user_id, status=status, limit=limit, offset=offset
    )
    data = PaginatedData(
        items=results, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Experiments retrieved successfully")


@router.get("/experiments/{experiment_id}")
def get_experiment(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.get_experiment(experiment_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Experiment retrieved successfully")


@router.delete("/experiments/{experiment_id}", status_code=204)
def delete_experiment(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ExperimentService = Depends(experiment_service),
) -> None:
    call(lambda: service.delete_experiment(experiment_id, principal.user_id))
    auth.audit("experiment_delete", principal.user_id, experiment_id)


@router.post("/experiments/{experiment_id}/run", status_code=202)
def run_experiment(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.start_experiment(experiment_id, principal.user_id))
    auth.audit("experiment_run", principal.user_id, experiment_id)
    return ApiResponse(success=True, data=result, message="Experiment started successfully")


@router.get("/experiments/{experiment_id}/results")
def experiment_results(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.results(experiment_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Experiment results retrieved")


@router.get("/experiments/{experiment_id}/comparison")
def experiment_comparison(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.comparison(experiment_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Comparison report retrieved")


@router.get("/experiments/{experiment_id}/panel")
def experiment_panel(
    experiment_id: str,
    principal: Principal = Depends(current_user),
    service: ExperimentService = Depends(experiment_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.panel(experiment_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Panel data retrieved")
