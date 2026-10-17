"""Owner-scoped evaluation result query endpoints."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.schemas import ApiResponse, PaginatedData
from api.services import EvaluationResultsService

router = APIRouter(prefix="/api/v1", tags=["evaluation-results"])
T = TypeVar("T")


def evaluation_results_service(request: Request) -> EvaluationResultsService:
    return cast(EvaluationResultsService, request.app.state.evaluation_results)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


def _page(limit: int, offset: int) -> tuple[int, int]:
    return (limit if 1 <= limit <= 100 else 20, max(0, offset))


@router.get("/results/problems/{problem_id}")
def problem_history(
    problem_id: str,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit, offset = _page(limit, offset)
    items, total = call(
        lambda: service.problem_history(
            principal.user_id, problem_id, status=status, limit=limit, offset=offset
        )
    )
    data = PaginatedData(
        items=items, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Problem results retrieved")


@router.get("/results")
def list_results(
    strategy: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    status: str | None = None,
    limit: int = 20,
    offset: int = 0,
    sort: str = "completed_at",
    order: str = "desc",
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[PaginatedData[dict]]:
    limit, offset = _page(limit, offset)
    if sort not in {"completed_at", "created_at"}:
        sort = "completed_at"
    items, total = call(
        lambda: service.list_runs(
            principal.user_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
            status=status,
            limit=limit,
            offset=offset,
            sort=sort,
            order=order,
        )
    )
    data = PaginatedData(
        items=items, total=total, limit=limit, offset=offset, has_more=offset + limit < total
    )
    return ApiResponse(success=True, data=data, message="Evaluation results retrieved")


@router.get("/results/{run_id}")
def get_result(
    run_id: str,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    service: EvaluationResultsService = Depends(evaluation_results_service),
) -> ApiResponse[dict]:
    limit, offset = _page(limit, offset)
    data = call(lambda: service.detail(principal.user_id, run_id, limit=limit, offset=offset))
    return ApiResponse(success=True, data=data, message="Evaluation result retrieved")
