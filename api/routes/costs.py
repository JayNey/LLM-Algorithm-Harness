"""Cost, budget, alert and pricing endpoints (issue #154)."""

from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import APIRouter, Depends, HTTPException, Path as PathParam, Request

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


@router.get("/pricing")
def pricing_catalog(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
) -> ApiResponse[dict]:
    result = service.pricing_catalog()
    return ApiResponse(success=True, data=result, message="Pricing catalog retrieved successfully")


@router.get("/pricing/{model_id}/history")
def pricing_history(
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
    model_id: str = PathParam(..., max_length=200),
) -> ApiResponse[list[dict]]:
    result = service.pricing_history(model_id)
    return ApiResponse(success=True, data=result, message="Pricing history retrieved successfully")


@router.post("/pricing/{model_id}", status_code=201)
def set_pricing_override(
    request: PricingOverrideRequest,
    principal: Principal = Depends(current_user),
    service: CostService = Depends(cost_service),
    model_id: str = PathParam(..., max_length=200),
) -> ApiResponse[dict]:
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
