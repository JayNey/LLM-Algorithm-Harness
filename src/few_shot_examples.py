"""Historical example identity and target-overlap rules."""

from dataclasses import dataclass
from urllib.parse import urlsplit

from src.models import Problem


@dataclass
class ExampleProblem:
    """Public problem information needed by historical examples."""

    problem_id: str
    title: str
    description: str
    difficulty: str
    tags: list[str]
    source_platform: str = "legacy"
    source_problem_id: str | None = None
    source_url: str | None = None
    source_version: str | None = None


def _source_url(value: str | None) -> str:
    if not value:
        return ""
    try:
        parts = urlsplit(value.strip())
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            return ""
        return parts.netloc.lower() + parts.path.rstrip("/")
    except ValueError:
        return ""


def overlap_reason(
    target: Problem | ExampleProblem, candidate: Problem | ExampleProblem
) -> str | None:
    """Identify provable duplicates without guessing semantic equivalence."""
    if target.problem_id.strip() == candidate.problem_id.strip():
        return "problem_id"
    platform = target.source_platform.strip().casefold()
    source_id = (target.source_problem_id or "").strip()
    if (
        platform
        and source_id
        and platform == candidate.source_platform.strip().casefold()
        and source_id == (candidate.source_problem_id or "").strip()
    ):
        return "source_identity"
    url = _source_url(target.source_url)
    if url and url == _source_url(candidate.source_url):
        return "source_url"
    description = " ".join(target.description.casefold().split())
    if description and description == " ".join(candidate.description.casefold().split()):
        return "description"
    return None
