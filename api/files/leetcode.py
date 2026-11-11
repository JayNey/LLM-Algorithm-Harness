"""Request validation and candidate metadata for LeetCode batch imports."""

import re
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_LEETCODE_BATCH = 50
LeetCodeDifficulty = Literal["easy", "medium", "hard"]
LeetCodeSlug = Annotated[str, Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=150)]


class LeetCodePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tags: list[LeetCodeSlug] = Field(default_factory=list, max_length=10)
    difficulty: LeetCodeDifficulty | None = None
    limit: int = Field(default=20, strict=True, ge=1, le=MAX_LEETCODE_BATCH)

    @field_validator("tags", mode="before")
    @classmethod
    def normalize_tags(cls, value: object) -> object:
        if isinstance(value, list):
            return [
                re.sub(r"\s+", "-", item.strip().lower()) if isinstance(item, str) else item
                for item in value
            ]
        return value

    @model_validator(mode="after")
    def require_filter(self) -> Self:
        if not self.tags and self.difficulty is None:
            raise ValueError("Choose a tag or difficulty")
        return self


class LeetCodeCandidate(BaseModel):
    slug: LeetCodeSlug
    number: str
    title: str
    difficulty: LeetCodeDifficulty
    tags: list[str]
    source_url: str
