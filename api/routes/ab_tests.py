"""A/B test and stateless analysis endpoints (issue #156)."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth.dependencies import auth_service, current_user
from api.auth.service import AuthService, Principal
from api.experiment_models import ABTestCreateRequest, OptimizeRequest, ParetoAnalyzeRequest
from api.schemas import ApiResponse, PaginatedData
from api.services import ABTestService
from src.cost_optimizer import build_advisory
from src.pareto import build_pareto_analysis

router = APIRouter(prefix="/api/v1", tags=["ab-tests", "analysis"])
T = TypeVar("T")


def ab_test_service(request: Request) -> ABTestService:
    return cast(ABTestService, request.app.state.ab_tests)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


# -- A/B tests ---------------------------------------------------------------


@router.post("/ab-tests", status_code=201)
def create_ab_test(
    request: ABTestCreateRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ABTestService = Depends(ab_test_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.create_test(request, principal.user_id))
    auth.audit("ab_test_create", principal.user_id, result["id"])
    return ApiResponse(success=True, data=result, message="A/B test created successfully")


@router.get("/ab-tests")
def list_ab_tests(
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: ABTestService = Depends(ab_test_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit = limit if 1 <= limit <= 100 else 20
    offset = max(0, offset)
    results, total = service.list_tests(
        principal.user_id, status=status, limit=limit, offset=offset
    )
    data = PaginatedData(
        items=results, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="A/B tests retrieved successfully")


@router.get("/ab-tests/{test_id}")
def get_ab_test(
    test_id: str,
    principal: Principal = Depends(current_user),
    service: ABTestService = Depends(ab_test_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.get_test(test_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="A/B test retrieved successfully")


@router.delete("/ab-tests/{test_id}", status_code=204)
def delete_ab_test(
    test_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ABTestService = Depends(ab_test_service),
) -> None:
    call(lambda: service.delete_test(test_id, principal.user_id))
    auth.audit("ab_test_delete", principal.user_id, test_id)


@router.post("/ab-tests/{test_id}/run", status_code=202)
def run_ab_test(
    test_id: str,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: ABTestService = Depends(ab_test_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.start_test(test_id, principal.user_id))
    auth.audit("ab_test_run", principal.user_id, test_id)
    return ApiResponse(success=True, data=result, message="A/B test started successfully")


@router.get("/ab-tests/{test_id}/results")
def ab_test_results(
    test_id: str,
    principal: Principal = Depends(current_user),
    service: ABTestService = Depends(ab_test_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.results(test_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="A/B test results retrieved")


# -- stateless analysis ------------------------------------------------------


@router.post("/pareto/analyze")
def pareto_analyze(
    request: ParetoAnalyzeRequest,
    _principal: Principal = Depends(current_user),
) -> ApiResponse[dict]:
    try:
        analysis = build_pareto_analysis(
            request.comparisons,
            budgets=request.budgets,
            accuracy_metric=request.accuracy_metric,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return ApiResponse(success=True, data=analysis, message="Pareto analysis completed")


@router.post("/optimize")
def optimize(
    request: OptimizeRequest,
    _principal: Principal = Depends(current_user),
) -> ApiResponse[dict]:
    try:
        advisory = build_advisory(
            request.comparison,
            budget=request.budget,
            min_accuracy=request.min_accuracy,
            objective=request.objective,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return ApiResponse(success=True, data=advisory, message="Cost optimization advisory generated")
