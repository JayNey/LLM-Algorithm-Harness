"""Unified API schemas and response wrappers."""

from typing import TypeVar, Generic, Optional, Any
from pydantic import BaseModel, Field

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Unified API response wrapper."""

    success: bool = Field(..., description="Whether the request was successful")
    data: Optional[T] = Field(None, description="Response data")
    message: str = Field(..., description="Response message")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "data": {},
                "message": "Operation successful",
            }
        }


class PaginatedData(BaseModel, Generic[T]):
    """Paginated response data."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., ge=0, description="Total number of items")
    limit: int = Field(..., ge=1, description="Number of items per page")
    offset: int = Field(..., ge=0, description="Current offset")
    has_more: bool = Field(..., description="Whether there are more items")

    class Config:
        json_schema_extra = {
            "example": {
                "items": [],
                "total": 100,
                "limit": 20,
                "offset": 0,
                "has_more": True,
            }
        }


class ProgressInfo(BaseModel):
    """Task progress information."""

    completed: int = Field(..., ge=0, description="Number of completed problems")
    total: int = Field(..., ge=0, description="Total number of problems")
    percentage: float = Field(..., ge=0, le=100, description="Progress percentage")


class EvaluationResponse(BaseModel):
    """Evaluation task response model."""

    evaluation_id: str = Field(..., description="Unique evaluation ID")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    updated_at: str = Field(..., description="ISO 8601 update timestamp")
    status: str = Field(..., description="Task status: pending|running|completed|failed|cancelled")
    strategy_names: list[str] = Field(..., description="Strategies used in this evaluation")
    problem_count: int = Field(..., ge=0, description="Total number of problems")
    spent_usd: float = Field(..., ge=0, description="Amount spent so far in USD")
    budget_cap_usd: Optional[float] = Field(None, ge=0, description="Budget limit in USD")
    progress: ProgressInfo = Field(..., description="Execution progress")


class ExecutionResultResponse(BaseModel):
    """Single problem execution result response model."""

    result_id: str = Field(..., description="Unique result ID")
    problem_id: str = Field(..., description="Problem ID")
    strategy_name: str = Field(..., description="Strategy used")
    status: str = Field(..., description="Result status: pass|fail|error|timeout")
    execution_time_ms: float = Field(..., ge=0, description="Execution time in milliseconds")
    cost_usd: float = Field(..., ge=0, description="Cost in USD")
    output: Optional[str] = Field(None, description="Command output if available")
    error_message: Optional[str] = Field(None, description="Error message if failed")


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="API version")
    service: str = Field(..., description="Service name")
