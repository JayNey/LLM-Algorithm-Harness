"""Benchmark suite, run and learning curve endpoints (issue #156)."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from api.auth.dependencies import auth_service, current_user
from api.auth.service import AuthService, Principal
from api.experiment_models import (
    BenchmarkRunRequest,
    BenchmarkRunResponse,
    BenchmarkRunStatus,
    BenchmarkSuiteCreateRequest,
    BenchmarkSuiteUpdateRequest,
)
from api.schemas import ApiResponse, PaginatedData
from api.services import BenchmarkService

router = APIRouter(prefix="/api/v1", tags=["benchmarks"])
T = TypeVar("T")


def benchmark_service(request: Request) -> BenchmarkService:
    return cast(BenchmarkService, request.app.state.benchmarks)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


@router.get("/benchmarks/suites")
def list_suites(
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[PaginatedData[dict]]:
    results = service.list_suites(principal.user_id)
    data = PaginatedData(
        items=results, total=len(results), limit=len(results) or 1, offset=0, has_more=False
    )
    return ApiResponse(success=True, data=data, message="Benchmark suites retrieved successfully")


@router.post("/benchmarks/suites", status_code=201)
def create_suite(
    request: BenchmarkSuiteCreateRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.create_suite(request, principal.user_id))
    auth.audit("benchmark_suite_create", principal.user_id, result["id"])
    return ApiResponse(success=True, data=result, message="Benchmark suite created successfully")


@router.get("/benchmarks/suites/{suite_id}")
def get_suite(
    suite_id: str,
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.get_suite(suite_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Benchmark suite retrieved successfully")


@router.patch("/benchmarks/suites/{suite_id}")
def update_suite(
    suite_id: str,
    request: BenchmarkSuiteUpdateRequest,
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.update_suite(suite_id, request, principal.user_id))
    return ApiResponse(success=True, data=result, message="Benchmark suite updated successfully")


@router.post("/benchmarks/suites/{suite_id}/run", status_code=202)
def run_suite(
    suite_id: str,
    request: BenchmarkRunRequest,
    principal: Principal = Depends(current_user),
    auth: AuthService = Depends(auth_service),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.start_run(suite_id, request, principal.user_id))
    auth.audit("benchmark_run", principal.user_id, result["id"])
    return ApiResponse(success=True, data=result, message="Benchmark run started successfully")


@router.get("/benchmarks/suites/{suite_id}/runs")
def list_runs(
    suite_id: str,
    status: BenchmarkRunStatus | None = Query(None, description="Filter by one run status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[PaginatedData[BenchmarkRunResponse]]:
    """List owned runs, newest first by created_at then id, filtering before pagination."""
    results, total = call(
        lambda: service.list_runs(suite_id, principal.user_id, status, limit, offset)
    )
    data = PaginatedData[BenchmarkRunResponse](
        items=results, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Benchmark runs retrieved successfully")


@router.get("/benchmarks/runs/{run_id}")
def get_run(
    run_id: str,
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.get_run(run_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Benchmark run retrieved successfully")


@router.get("/benchmarks/learning-curve/{suite_id}")
def learning_curve(
    suite_id: str,
    principal: Principal = Depends(current_user),
    service: BenchmarkService = Depends(benchmark_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.learning_curve(suite_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Learning curve retrieved successfully")
