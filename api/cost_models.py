"""Request models for cost, budget, alert and pricing APIs (issue #154)."""

from pydantic import BaseModel, Field


class BudgetUpsertRequest(BaseModel):
    """Upsert the caller's single budget configuration."""

    global_cap_usd: float | None = Field(None, gt=0)
    difficulty_caps: dict[str, float] | None = None
    action: str = Field("pause", pattern="^(pause|downgrade)$")


class AlertRuleCreateRequest(BaseModel):
    """Create a cost alert rule."""

    name: str = Field("", max_length=200)
    threshold_pct: int = Field(..., ge=1, le=100)
    channel: str = Field(..., pattern="^(slack|webhook|smtp|log)$")
    target: str = Field("", max_length=1000)
    enabled: bool = True


class AlertRuleUpdateRequest(BaseModel):
    """Update an existing cost alert rule."""

    name: str | None = Field(None, max_length=200)
    threshold_pct: int | None = Field(None, ge=1, le=100)
    channel: str | None = Field(None, pattern="^(slack|webhook|smtp|log)$")
    target: str | None = Field(None, max_length=1000)
    enabled: bool | None = None


class PricingOverrideRequest(BaseModel):
    """Append a custom pricing version for one model (USD per 1k tokens)."""

    prompt_per_1k: float = Field(..., gt=0)
    completion_per_1k: float = Field(..., gt=0)
