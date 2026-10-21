"""普通用户可读的评估策略、来源与分页题目元数据。"""

from typing import cast

from fastapi import APIRouter, Depends, Query, Request, Response

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.evaluation_options import EvaluationOptions, ProblemOption, ProblemSourceFilter
from api.schemas import ApiResponse, PaginatedData
from api.services.evaluation_options_service import EvaluationOptionsService

router = APIRouter(prefix="/api/v1/evaluation-options", tags=["evaluation-options"])


def evaluation_options_service(request: Request) -> EvaluationOptionsService:
    return cast(EvaluationOptionsService, request.app.state.evaluation_options)


@router.get("")
def options(
    response: Response,
    principal: Principal = Depends(current_user),
    service: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[EvaluationOptions]:
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(
        success=True, data=service.options(principal.user_id), message="Evaluation options"
    )


@router.get("/problems")
def problems(
    response: Response,
    source: ProblemSourceFilter = Query("all"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(current_user),
    service: EvaluationOptionsService = Depends(evaluation_options_service),
) -> ApiResponse[PaginatedData[ProblemOption]]:
    response.headers["Cache-Control"] = "no-store"
    return ApiResponse(
        success=True,
        data=service.problems(principal.user_id, source, limit, offset),
        message="Evaluation problems",
    )
