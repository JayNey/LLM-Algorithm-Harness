"""API request and response models."""

from pydantic import BaseModel, Field, field_validator


class EvaluationCreateRequest(BaseModel):
    """Request model for creating a new evaluation."""

    api_key_id: str = Field(
        ..., min_length=1, max_length=64, description="ID of your stored LLM API key"
    )
    model: str = Field(..., min_length=1, description="Model name used to execute the evaluation")
    problem_ids: list[str] = Field(..., min_length=1, description="List of problem IDs to evaluate")
    strategy_names: list[str] = Field(
        ..., min_length=1, description="List of strategy names to use"
    )
    budget_cap_usd: float | None = Field(None, ge=0, description="Maximum budget in USD")
    timeout_seconds: int = Field(300, ge=1, description="Timeout per problem in seconds")
    max_concurrency: int = Field(5, ge=1, description="Max concurrent problems")

    @field_validator("strategy_names")
    @classmethod
    def _reject_duplicate_strategy_names(cls, v: list[str]) -> list[str]:
        """拒绝含重复项的 strategy_names（verify I-4）。

        重复值会让 _create_task_units 生成同 (strategy, problem) 的多个单元，
        但幂等键 (evaluation_id, problem_id, strategy_name) 只落 1 行
        EvaluationResult，而 completed_count/spent_usd 却累加多次，造成单元计数
        与实际结果行数不一致的脏聚合。在入口即返回 400（validation_error），
        杜绝下游歧义，且不改变既有合法请求的行为。

        使用 field_validator（而非 model_validator(mode="after")），pydantic 会把错误
        定位到字段本身，全局校验错误处理器的 details 键为 "strategy_names"，
        客户端可按字段定位。
        """
        if len(set(v)) != len(v):
            raise ValueError("strategy_names must not contain duplicates")
        return v

    @field_validator("problem_ids")
    @classmethod
    def _reject_duplicate_problem_ids(cls, v: list[str]) -> list[str]:
        """拒绝含重复项的 problem_ids（verify I-4），原因同上。

        details 键为 "problem_ids"，便于客户端按字段定位。
        """
        if len(set(v)) != len(v):
            raise ValueError("problem_ids must not contain duplicates")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "problem_ids": ["1", "2", "3"],
                "api_key_id": "your-stored-key-id",
                "model": "gpt-4o-mini",
                "strategy_names": ["vanilla", "chain_of_thought"],
                "budget_cap_usd": 10.0,
                "timeout_seconds": 300,
                "max_concurrency": 5,
            }
        }


class EvaluationUpdateRequest(BaseModel):
    """Request model for updating an evaluation (only pending tasks)."""

    budget_cap_usd: float | None = Field(None, ge=0, description="Updated budget cap")
    timeout_seconds: int | None = Field(None, ge=1, description="Updated timeout")


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    limit: int = Field(20, ge=1, le=100, description="Number of items per page")
    offset: int = Field(0, ge=0, description="Number of items to skip")


class AsyncTaskCreateRequest(BaseModel):
    """Request model for creating an async task."""

    task_type: str = Field(
        ..., min_length=1, max_length=32, description="Task type (e.g., evaluation, experiment)"
    )
    entity_id: str = Field(..., min_length=1, description="Related entity ID")
    celery_task_name: str = Field(
        ...,
        min_length=1,
        description="Celery task name to execute (e.g., src.tasks.evaluation.run_evaluation_task)",
    )
    celery_task_args: list | None = Field(None, description="Positional arguments for Celery task")
    celery_task_kwargs: dict | None = Field(None, description="Keyword arguments for Celery task")

    class Config:
        json_schema_extra = {
            "example": {
                "task_type": "evaluation",
                "entity_id": "eval-123",
                "celery_task_name": "src.tasks.evaluation.run_evaluation_task",
                "celery_task_args": ["eval-123"],
                "celery_task_kwargs": {"user_id": "user-456"},
            }
        }
