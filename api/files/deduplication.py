"""Owner-scoped, read-only duplicate review and immutable merge versions."""

import hashlib
import json
from itertools import combinations
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from api.files.governance import DatasetVersion, ItemId, VersionName
from api.files.store import FileStore
from src.problem_utils.utils.deduplication import (
    find_fingerprint_duplicates,
    find_similar_pairs,
    merge_problems,
    select_primary_problem,
)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class DeduplicationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    threshold: float = Field(0.9, ge=0, le=1)


class MergeSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    group_id: ItemId
    primary_id: ItemId


class DeduplicationSaveRequest(DeduplicationRequest):
    preview_token: str = Field(pattern=r"^[a-f0-9]{64}\.[a-f0-9]{64}$")
    name: VersionName
    groups: list[MergeSelection] = Field(min_length=1, max_length=100000)


class DuplicateMatch(BaseModel):
    left_id: str
    right_id: str
    fingerprint: bool
    similarity: float | None


class DuplicateGroup(BaseModel):
    group_id: str
    recommended_primary_id: str
    problems: list[dict[str, Any]]
    matches: list[DuplicateMatch]
    merges: dict[str, dict[str, Any]]


class DeduplicationPreview(BaseModel):
    preview_token: str
    groups: list[DuplicateGroup]


def preview_deduplication(
    store: FileStore,
    owner: str,
    request: DeduplicationRequest,
    expected_source: str | None = None,
) -> tuple[DeduplicationPreview, list[dict[str, Any]]]:
    revision, rows = store.dataset_snapshot(owner)
    if expected_source is not None and revision != expected_source:
        raise HTTPException(409, "Deduplication preview is stale; scan again")
    # Match the personal-library reader's last-record-wins handling of legacy IDs.
    problems = list({p["problem_id"]: p for p in rows}.values())
    fingerprint_groups = find_fingerprint_duplicates(problems)
    fingerprints = {pair for group in fingerprint_groups for pair in combinations(group, 2)}
    pairs = find_similar_pairs(problems, threshold=request.threshold, include_pairs=fingerprints)
    similarities = {(i, j): score for i, j, score in pairs}
    groups = list(fingerprint_groups)
    used = {index for group in groups for index in group}
    # Same non-overlapping group precedence as the CLI.
    for i, j, _ in pairs:
        if i not in used and j not in used:
            groups.append([i, j])
            used.update((i, j))
    candidates = []
    for group in groups:
        members = [problems[index] for index in group]
        ids = [p["problem_id"] for p in members]
        merges = {
            primary["problem_id"]: merge_problems(
                primary, [other for other in members if other is not primary]
            )
            for primary in members
        }
        candidates.append(
            DuplicateGroup(
                group_id=digest(ids),
                recommended_primary_id=ids[select_primary_problem(members)],
                problems=members,
                merges=merges,
                matches=[
                    DuplicateMatch(
                        left_id=problems[i]["problem_id"],
                        right_id=problems[j]["problem_id"],
                        fingerprint=(i, j) in fingerprints,
                        similarity=similarities.get((i, j)),
                    )
                    for i, j in combinations(group, 2)
                    if (i, j) in fingerprints or (i, j) in similarities
                ],
            )
        )
    content = [owner, request.threshold, [group.model_dump() for group in candidates]]
    return (
        DeduplicationPreview(preview_token=revision + "." + digest(content), groups=candidates),
        problems,
    )


def save_deduplication(
    store: FileStore,
    owner: str,
    request: DeduplicationSaveRequest,
) -> DatasetVersion:
    selections = {group.group_id: group.primary_id for group in request.groups}
    if len(selections) != len(request.groups):
        raise HTTPException(400, "Duplicate group selection")
    confirmation = digest(
        [owner, request.preview_token, request.threshold, request.name, selections]
    )
    previous = store.dataset_confirmation(owner, confirmation)
    if previous is not None:
        return DatasetVersion.model_validate(previous)
    source = request.preview_token.split(".", 1)[0]
    preview, problems = preview_deduplication(
        store, owner, DeduplicationRequest(threshold=request.threshold), source
    )
    if preview.preview_token != request.preview_token:
        raise HTTPException(409, "Deduplication preview is stale; scan again")
    candidates = {group.group_id: group for group in preview.groups}
    removed = set()
    replacements = {}
    for group_id, primary in selections.items():
        group = candidates.get(group_id)
        if group is None or primary not in group.merges:
            raise HTTPException(400, "Invalid duplicate group or primary")
        removed.update(p["problem_id"] for p in group.problems if p["problem_id"] != primary)
        replacements[primary] = group.merges[primary]
    updated = [
        replacements.get(p["problem_id"], p) for p in problems if p["problem_id"] not in removed
    ]
    return DatasetVersion.model_validate(
        store.save_dataset_version(
            owner, source, request.name, updated, confirmation_key=confirmation
        )
    )
