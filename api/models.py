"""API request and response models."""

from typing import Any, Optional
from pydantic import BaseModel, Field


class EvaluationCreateRequest(BaseModel):
    """Request model for creating a new evaluation."""

    problem_ids: list[str] = Field(..., min_items=1, description="List of problem IDs to evaluate")
    strategy_names: list[str] = Field(..., min_items=1, description="List of strategy names to use")
    budget_cap_usd: Optional[float] = Field(
        None, ge=0, description="Maximum budget in USD"
    )
    timeout_seconds: int = Field(300, ge=1, description="Timeout per problem in seconds")
    max_concurrency: int = Field(5, ge=1, description="Max concurrent problems")

    class Config:
        json_schema_extra = {
            "example": {
                "problem_ids": ["1", "2", "3"],
                "strategy_names": ["vanilla", "chain_of_thought"],
                "budget_cap_usd": 10.0,
                "timeout_seconds": 300,
                "max_concurrency": 5,
            }
        }


class EvaluationUpdateRequest(BaseModel):
    """Request model for updating an evaluation (only pending tasks)."""

    budget_cap_usd: Optional[float] = Field(None, ge=0, description="Updated budget cap")
    timeout_seconds: Optional[int] = Field(None, ge=1, description="Updated timeout")


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    limit: int = Field(20, ge=1, le=100, description="Number of items per page")
    offset: int = Field(0, ge=0, description="Number of items to skip")
