"""Cost, budget, alert and pricing endpoints (issue #154)."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi import Path as PathParam

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.cost_models import (
    AlertRuleCreateRequest,
    AlertRuleUpdateRequest,
    BudgetUpsertRequest,
    PricingOverrideRequest,
)
from api.schemas import ApiResponse
from api.services.cost_service import CostService

router = APIRouter(prefix="/api/v1", tags=["costs", "budgets", "alerts", "pricing", "reports"])
T = TypeVar("T")


def cost_service(request: Request) -> CostService:
    return cast("CostService", request.app.state.cost)


def call(operation: Callable[[], T]) -> T:
    try:
        return operation()
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc)) from None


# -- cost queries ------------------------------------------------------------


@router.get("/costs/tasks/{task_id}")
def task_cost(
    task_id: str,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.task_cost(task_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Task cost retrieved successfully")


@router.get("/costs/summary")
def cost_summary(
    since: str | None = None,
    until: str | None = None,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.summary(principal.user_id, since, until))
    return ApiResponse(success=True, data=result, message="Cost summary retrieved successfully")


@router.get("/costs/trends")
def cost_trends(
    since: str | None = None,
    until: str | None = None,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.trends(principal.user_id, since, until))
    return ApiResponse(success=True, data=result, message="Cost trends retrieved successfully")


@router.get("/costs/breakdown")
def cost_breakdown(
    since: str | None = None,
    until: str | None = None,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.breakdown(principal.user_id, since, until))
    return ApiResponse(success=True, data=result, message="Cost breakdown retrieved successfully")


# -- budgets -----------------------------------------------------------------


@router.get("/budgets")
def get_budget(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.get_budget(principal.user_id)
    return ApiResponse(success=True, data=result, message="Budget retrieved successfully")


@router.post("/budgets", status_code=201)
def upsert_budget(
    request: BudgetUpsertRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.upsert_budget(request, principal.user_id)
    return ApiResponse(success=True, data=result, message="Budget saved successfully")


@router.patch("/budgets", status_code=200)
def update_budget(
    request: BudgetUpsertRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.upsert_budget(request, principal.user_id, partial=True)
    return ApiResponse(success=True, data=result, message="Budget updated successfully")


@router.get("/budgets/usage")
def budget_usage(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.budget_usage(principal.user_id)
    return ApiResponse(success=True, data=result, message="Budget usage retrieved successfully")


# -- alert rules -------------------------------------------------------------


@router.get("/alerts")
def list_alert_rules(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[list[dict]]:
    result = service.list_rules(principal.user_id)
    return ApiResponse(success=True, data=result, message="Alert rules retrieved successfully")


@router.post("/alerts", status_code=201)
def create_alert_rule(
    request: AlertRuleCreateRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.create_rule(request, principal.user_id))
    return ApiResponse(success=True, data=result, message="Alert rule created successfully")


@router.patch("/alerts/{rule_id}")
def update_alert_rule(
    rule_id: str,
    request: AlertRuleUpdateRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.update_rule(rule_id, request, principal.user_id))
    return ApiResponse(success=True, data=result, message="Alert rule updated successfully")


@router.delete("/alerts/{rule_id}", status_code=204)
def delete_alert_rule(
    rule_id: str,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> None:
    call(lambda: service.delete_rule(rule_id, principal.user_id))


@router.get("/alerts/history")
def alert_history(
    limit: int = 50,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[list[dict]]:
    result = service.alert_history(principal.user_id, limit=min(max(limit, 1), 200))
    return ApiResponse(success=True, data=result, message="Alert history retrieved successfully")


# -- pricing -----------------------------------------------------------------

PRICING_MODEL_ID_DESCRIPTION = (
    "完整模型 ID（非空，最多 200 字符），支持 Qwen/Qwen2.5-7B-Instruct 等含斜杠名称。"
    "客户端用 encodeURIComponent 对完整 ID 编码一次：保存地址为 "
    "/api/v1/pricing/Qwen%2FQwen2.5-7B-Instruct，查询历史在该地址后追加 /history。"
    "字面 %2F 须编码为 %252F；服务器仅解码一次，保存响应和目录键保留原值。"
    "反向代理须原样转发编码路径；gpt-4 等普通模型地址保持兼容。"
)


@router.get("/pricing")
def pricing_catalog(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.pricing_catalog()
    return ApiResponse(success=True, data=result, message="Pricing catalog retrieved successfully")


# Keep the history suffix explicit before the catch-all model path.
# ASGI has already decoded the path; do not unquote model_id again.
@router.get("/pricing/{model_id:path}/history")
def pricing_history(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
    model_id: str = PathParam(..., max_length=200, description=PRICING_MODEL_ID_DESCRIPTION),
) -> ApiResponse[list[dict]]:
    if not model_id:
        raise HTTPException(400, "Model ID must not be empty")
    result = service.pricing_history(model_id)
    return ApiResponse(success=True, data=result, message="Pricing history retrieved successfully")


@router.post("/pricing/{model_id:path}", status_code=201)
def set_pricing_override(
    request: PricingOverrideRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
    model_id: str = PathParam(..., max_length=200, description=PRICING_MODEL_ID_DESCRIPTION),
) -> ApiResponse[dict]:
    if not model_id:
        raise HTTPException(400, "Model ID must not be empty")
    result = service.set_pricing_override(model_id, request, principal.user_id)
    return ApiResponse(success=True, data=result, message="Pricing override saved successfully")


# -- reports -----------------------------------------------------------------


@router.get("/reports/cost/{task_id}")
def task_cost_report(
    task_id: str,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = call(lambda: service.task_report(task_id, principal.user_id))
    return ApiResponse(success=True, data=result, message="Task cost report generated")


@router.get("/reports/cost-optimization")
def cost_optimization_report(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.cost_optimization_report(principal.user_id)
    return ApiResponse(success=True, data=result, message="Cost optimization report generated")
