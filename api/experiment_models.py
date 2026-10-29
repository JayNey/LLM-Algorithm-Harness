"""Request models for experiment, benchmark and A/B test APIs (issue #156)."""

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from typing_extensions import Self

from src.ab_testing import PromptVariant
from src.models import ProblemBudget, StrategyConfig


class ModelSpec(BaseModel):
    """One model arm of an experiment; keys resolve from the auth store."""

    model: str = Field(..., min_length=1, description="Model name")
    base_url: str | None = Field(None, description="Optional base URL override")
    temperature: float | None = Field(None, ge=0.0, le=2.0)
    api_key_id: str | None = Field(
        None, description="Per-model key override; falls back to the request-level key"
    )


class DatasetRequest(BaseModel):
    """Exactly one owner-scoped collection or server-constrained legacy path."""

    dataset_id: str | None = Field(None, min_length=1, max_length=128)
    dataset_path: str | None = Field(None, min_length=1)

    @field_validator("dataset_id", "dataset_path")
    @classmethod
    def nonblank_source(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Dataset source must not be blank")
        return value

    @model_validator(mode="after")
    def exclusive_source(self) -> Self:
        if (self.dataset_id is None) == (self.dataset_path is None):
            raise ValueError("Provide exactly one of dataset_id or dataset_path")
        return self


class ExperimentCreateRequest(DatasetRequest):
    """Create a fixed-budget experiment."""

    name: str = Field("", max_length=200)
    models: list[ModelSpec] = Field(..., min_length=1)
    strategies: list[StrategyConfig] = Field(..., min_length=1)
    repeats: int = Field(1, ge=1)
    budget: ProblemBudget | None = None
    execution: str = Field("serial", pattern="^(serial|parallel)$")
    max_workers: int = Field(4, ge=1, le=16)
    problem_filters: dict[str, Any] | None = None
    api_key_id: str = Field(..., min_length=1, description="Default key for all model arms")


class BenchmarkSuiteCreateRequest(BaseModel):
    """Create a benchmark suite."""

    name: str = Field(..., min_length=1, max_length=200)
    problems: list[str] = Field(..., min_length=1)
    version: str = Field("1.0", max_length=32)
    description: str | None = None
    frozen: bool = False


class BenchmarkSuiteUpdateRequest(BaseModel):
    """Update an unfrozen benchmark suite."""

    problems: list[str] | None = Field(None, min_length=1)
    version: str | None = Field(None, max_length=32)
    description: str | None = None
    frozen: bool | None = None


class BenchmarkRunRequest(DatasetRequest):
    """Run a benchmark suite once."""

    api_key_id: str = Field(..., min_length=1)
    model: str = Field(..., min_length=1)
    strategies: list[StrategyConfig] = Field(default_factory=list)
    budget_cap_usd: float | None = Field(None, gt=0)
    problem_filters: dict[str, Any] | None = None


BenchmarkRunStatus = Literal["pending", "running", "paused", "completed", "failed", "cancelled"]


class BenchmarkRunResponse(BaseModel):
    """Owner-scoped run history entry; unavailable values remain null."""

    id: str
    suite_id: str
    task_id: str | None
    status: BenchmarkRunStatus
    model: str
    dataset_snapshot: dict[str, Any] | None
    accuracy: float | None
    cost_usd: float | None
    error_message: str | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None


class ABTestCreateRequest(DatasetRequest):
    """Create an A/B prompt test."""

    name: str = Field("", max_length=200)
    model: ModelSpec
    strategy: StrategyConfig
    prompt_variants: list[PromptVariant] = Field(..., min_length=2, max_length=2)
    baseline_id: str | None = None
    seed: int = Field(42, ge=0)
    max_workers: int = Field(1, ge=1, le=20)
    problem_filters: dict[str, Any] | None = None
    api_key_id: str = Field(..., min_length=1)


class ParetoAnalyzeRequest(BaseModel):
    """Stateless Pareto analysis over comparison payloads."""

    comparisons: list[dict[str, Any]] = Field(..., min_length=1)
    budgets: list[float] = Field(default_factory=list)
    accuracy_metric: str = Field("overall", pattern="^(overall|formal)$")


class OptimizeRequest(BaseModel):
    """Stateless cost optimization advisory over one comparison payload."""

    comparison: dict[str, Any]
    budget: float | None = Field(None, gt=0)
    min_accuracy: float = Field(0.0, ge=0.0, le=1.0)
    objective: str = Field("best_value")
