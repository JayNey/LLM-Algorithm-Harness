"""Preview and apply reviewed changes to an owner's personal dataset."""

import hashlib
import json
from typing import Annotated, Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from api.files.store import FileStore
from api.services.evaluation_results_service import EvaluationResultsService
from src.difficulty_calibration import (
    DEFAULT_EASY_THRESHOLD,
    DEFAULT_HARD_THRESHOLD,
    DifficultyCalibrator,
)
from src.utils.tag_manager import TagManager

ItemId = Annotated[str, StringConstraints(min_length=1, max_length=256)]
VersionName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]


class GovernanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_ids: list[ItemId] = Field(min_length=1, max_length=500)
    run_ids: list[ItemId] = Field(default_factory=list, max_length=100)
    easy_threshold: float = Field(DEFAULT_EASY_THRESHOLD, ge=0, le=1)
    hard_threshold: float = Field(DEFAULT_HARD_THRESHOLD, ge=0, le=1)

    @model_validator(mode="after")
    def validate_selection(self) -> "GovernanceRequest":
        if len(set(self.problem_ids)) != len(self.problem_ids):
            raise ValueError("Select each problem once")
        if self.hard_threshold >= self.easy_threshold:
            raise ValueError("Hard threshold must be below easy threshold")
        return self


class ApprovedChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    problem_id: ItemId
    normalize_tags: bool = False
    suggested_tags: list[str] = Field(default_factory=list, max_length=100)
    apply_difficulty: bool = False


class GovernanceSaveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview: GovernanceRequest
    preview_token: str = Field(pattern=r"^[a-f0-9]{64}\.[a-f0-9]{64}$")
    name: VersionName
    changes: list[ApprovedChange] = Field(max_length=500)


class VersionProblem(BaseModel):
    problem_id: str
    title: str
    difficulty: str
    tags: list[str] = Field(default_factory=list)


class TagSuggestion(BaseModel):
    tag: str
    confidence: float
    matched_keywords: list[str]
    reason: str


class ProblemChange(BaseModel):
    problem_id: str
    title: str
    original_tags: list[str]
    standard_tags: list[str]
    suggestions: list[TagSuggestion]
    original_difficulty: str
    suggested_difficulty: str
    sample_count: int
    pass_rate: float | None


class GovernancePreview(BaseModel):
    preview_token: str
    problems: list[ProblemChange]


class DatasetVersion(BaseModel):
    id: str
    name: str
    problem_count: int


class DatasetVersionDetail(DatasetVersion):
    problems: list[VersionProblem]


def preview_governance(
    store: FileStore,
    history: EvaluationResultsService,
    owner: str,
    request: GovernanceRequest,
    expected_source: str | None = None,
) -> tuple[GovernancePreview, dict[str, dict[str, Any]]]:
    revision, dataset = store.dataset_snapshot(owner)
    if expected_source is not None and revision != expected_source:
        raise HTTPException(409, "Governance preview is stale")
    personal = {problem["problem_id"]: problem for problem in dataset}
    if not set(request.problem_ids).issubset(personal):
        raise HTTPException(404, "Personal problem not found")
    problems = {pid: personal[pid] for pid in request.problem_ids}

    records = history.governance_history(owner, request.run_ids, request.problem_ids)
    calibrator = DifficultyCalibrator(
        easy_threshold=request.easy_threshold, hard_threshold=request.hard_threshold
    )
    stats = calibrator.collect_stats(records)
    tags = TagManager()
    changes = []
    for pid, problem in problems.items():
        original_tags = problem.get("tags") or []
        original_difficulty = problem["difficulty"]
        stat = stats.get(pid)
        rate = stat["success_rate"] if stat else None
        changes.append(
            ProblemChange(
                problem_id=pid,
                title=problem["title"],
                original_tags=original_tags,
                standard_tags=tags.normalize_tags(original_tags),
                suggestions=[
                    TagSuggestion.model_validate(suggestion)
                    for suggestion in tags.recommend_tags(
                        problem["title"], problem["description"], original_tags
                    )
                ],
                original_difficulty=original_difficulty,
                suggested_difficulty=(
                    calibrator.classify(rate) if rate is not None else original_difficulty
                ),
                sample_count=int(stat["total"]) if stat else 0,
                pass_rate=rate,
            )
        )

    content = json.dumps(
        [request.model_dump(), [change.model_dump() for change in changes]], sort_keys=True
    )
    token = revision + "." + hashlib.sha256(content.encode()).hexdigest()
    return GovernancePreview(preview_token=token, problems=changes), problems


def save_governance(
    store: FileStore, history: EvaluationResultsService, owner: str, request: GovernanceSaveRequest
) -> DatasetVersion:
    revision = request.preview_token.split(".", 1)[0]
    preview, originals = preview_governance(store, history, owner, request.preview, revision)
    if preview.preview_token != request.preview_token:
        raise HTTPException(409, "Governance preview is stale")
    changes = {change.problem_id: change for change in preview.problems}
    approved = {change.problem_id: change for change in request.changes}
    if len(approved) != len(request.changes) or not approved.keys() <= changes.keys():
        raise HTTPException(400, "Invalid governance selection")

    updated = originals.copy()
    applied = False
    for pid, approval in approved.items():
        change = changes[pid]
        allowed_tags = [suggestion.tag for suggestion in change.suggestions]
        chosen = set(approval.suggested_tags)
        if not chosen.issubset(allowed_tags):
            raise HTTPException(400, "Invalid tag suggestion")
        if approval.apply_difficulty and change.pass_rate is None:
            raise HTTPException(400, "No valid difficulty samples")
        tags = change.standard_tags if approval.normalize_tags else change.original_tags
        tags = [*tags, *(tag for tag in allowed_tags if tag in chosen)]
        difficulty = (
            change.suggested_difficulty if approval.apply_difficulty else change.original_difficulty
        )
        if tags != change.original_tags or difficulty != change.original_difficulty:
            updated[pid] = {**originals[pid], "tags": tags, "difficulty": difficulty}
            applied = True

    if not applied:
        raise HTTPException(400, "No approved changes to save")
    version = store.save_dataset_version(owner, revision, request.name, list(updated.values()))
    return DatasetVersion.model_validate(version)
