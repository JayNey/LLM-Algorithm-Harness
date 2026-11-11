"""用于真实评估创建流程的只读选项响应。"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator

ProblemSource = Literal["shared", "personal"]
ProblemSourceFilter = Literal["all", "shared", "personal"]


class StrategyOption(BaseModel):
    name: str


class SourceOption(BaseModel):
    id: ProblemSource
    label: str
    problem_count: int = Field(ge=0)


class ProblemOption(BaseModel):
    problem_id: str
    title: str
    difficulty: str | None
    source: ProblemSource


class EvaluationOptions(BaseModel):
    strategies: list[StrategyOption]
    sources: list[SourceOption]


class ModelOptions(BaseModel):
    source: Literal["provider_api"] = "provider_api"
    scope: Literal["user_api_key"] = "user_api_key"
    provider: str
    models: list[str]
    complete: bool


SelectionId = Annotated[str, StringConstraints(min_length=1, max_length=200)]


class ProblemSelection(BaseModel):
    problem_ids: list[SelectionId] = Field(min_length=1, max_length=100)

    @field_validator("problem_ids")
    @classmethod
    def unique_ids(cls, ids: list[str]) -> list[str]:
        if len(set(ids)) != len(ids):
            raise ValueError("Problem IDs must be unique")
        return ids


class RecommendationPreviewRequest(BaseModel):
    run_ids: list[SelectionId] = Field(min_length=1, max_length=20)
    source: ProblemSourceFilter = "all"
    min_samples: int = Field(default=1, ge=1, le=1000)
    failure_threshold: float = Field(default=0.5, gt=0, le=1)


class RecommendationWeakness(BaseModel):
    key: str
    failure_rate: float
    total: int


class RecommendedProblem(BaseModel):
    problem_id: str
    title: str
    difficulty: str | None
    reason: str
    matching_groups: list[str]
    failure_rate: float
    total: int


class RecommendationPreview(BaseModel):
    weaknesses: list[RecommendationWeakness]
    problems: list[RecommendedProblem]
    empty_reason: Literal["insufficient_history", "no_weaknesses", "no_candidates"] | None


class RecommendationSetCreate(ProblemSelection):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class RecommendationSetSummary(BaseModel):
    id: str
    name: str


class RecommendationSetDetail(RecommendationSetSummary):
    problems: list[ProblemOption]
    unavailable_count: int
