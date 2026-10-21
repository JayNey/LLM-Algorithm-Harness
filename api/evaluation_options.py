"""用于真实评估创建流程的只读选项响应。"""

from typing import Literal

from pydantic import BaseModel, Field

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
