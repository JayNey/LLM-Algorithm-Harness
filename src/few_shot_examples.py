"""Historical example identity and target-overlap rules."""

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.models import Problem, ProblemSnapshot
from src.utils.logging import get_logger

logger = get_logger(__name__)
EXAMPLE_CONTRACT_VERSION = "1.0"


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


@dataclass
class SimilarProblem:
    """A historical answer with retrieval scores and auditable origins."""

    problem: ExampleProblem | Problem
    solution_code: str
    similarity_score: float
    matching_tags: list[str]
    example_id: str = ""
    sources: list[dict[str, Any]] = field(default_factory=list)


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


def content_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _content(example: SimilarProblem) -> dict[str, Any]:
    snapshot = (
        ProblemSnapshot.from_problem(example.problem)
        if isinstance(example.problem, Problem)
        else ProblemSnapshot.model_validate(asdict(example.problem))
    )
    return {"problem_snapshot": snapshot.model_dump(), "solution_code": example.solution_code}


def example_reference(example: SimilarProblem) -> dict[str, Any]:
    return {
        "example_id": example.example_id or content_hash(_content(example)),
        "problem_id": example.problem.problem_id,
        "sources": example.sources,
    }


def create_manifest(
    examples: list[SimilarProblem], excluded: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Deduplicate content and aggregate origins in deterministic order."""
    entries: dict[str, dict[str, Any]] = {}
    for example in examples:
        content = _content(example)
        identity = content_hash(content)
        entry = entries.setdefault(identity, {"example_id": identity, **content, "sources": []})
        for source in example.sources:
            if source not in entry["sources"]:
                entry["sources"].append(source)
        entry["sources"].sort(key=lambda source: json.dumps(source, sort_keys=True))
    ordered = [entries[key] for key in sorted(entries)]
    return {
        "schema_version": EXAMPLE_CONTRACT_VERSION,
        "example_set_id": content_hash(
            {
                "schema_version": EXAMPLE_CONTRACT_VERSION,
                "examples": [
                    {k: v for k, v in entry.items() if k != "sources"} for entry in ordered
                ],
            }
        ),
        "examples": ordered,
        "excluded": excluded or [],
    }


def examples_from_manifest(manifest: dict[str, Any]) -> list[SimilarProblem]:
    if manifest.get("schema_version") != EXAMPLE_CONTRACT_VERSION:
        raise ValueError("Unsupported example collection version")
    examples = []
    for entry in manifest["examples"]:
        snapshot = ProblemSnapshot.model_validate(entry["problem_snapshot"])
        code = entry["solution_code"]
        if not isinstance(code, str) or not code.strip():
            raise ValueError("Invalid example solution")
        example = SimilarProblem(
            ExampleProblem(**snapshot.model_dump(exclude={"schema_version"})),
            code,
            0.0,
            [],
            sources=entry["sources"],
        )
        example.example_id = content_hash(_content(example))
        if example.example_id != entry["example_id"]:
            raise ValueError("Example content digest mismatch")
        examples.append(example)
    if create_manifest(examples)["example_set_id"] != manifest.get("example_set_id"):
        raise ValueError("Example collection digest mismatch")
    return examples


def load_manifest(path: Path, expected_id: str) -> dict[str, Any]:
    """Fail closed for explicitly pinned experiment inputs."""
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise ValueError("Example collection must be an object")
        examples_from_manifest(manifest)
        if not expected_id or manifest["example_set_id"] != expected_id:
            raise ValueError("Example collection identity mismatch")
        return manifest
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise ValueError("Invalid frozen example collection; start a new experiment") from exc


def _successful(row: dict[str, Any]) -> bool:
    if row.get("status") != "success" or row.get("evaluation_completed", True) is not True:
        return False
    code = row.get("generated_code")
    if not isinstance(code, str) or not code.strip():
        return False
    for result in [row, row.get("final_result"), row.get("hidden_result")]:
        if result is None:
            continue
        if not isinstance(result, dict):
            return False
        if "all_passed" in result and result["all_passed"] is not True:
            return False
        if result.get("status") in {"failed", "error", "timeout", "unsupported"}:
            return False
        tests = result.get("test_results", [])
        if not isinstance(tests, list) or any(
            not isinstance(test, dict) or test.get("passed") is not True for test in tests
        ):
            return False
    return True


def load_history(results_dir: Path = Path("results")) -> dict[str, Any]:
    examples: list[SimilarProblem] = []
    for path in sorted(results_dir.rglob("*_results.json")):
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(rows, list):
                raise ValueError("History root must be a result list")
        except (OSError, ValueError) as exc:
            logger.warning("historical_result_file_skipped", file=str(path), reason=str(exc))
            continue
        for index, row in enumerate(rows):
            source = {"file": str(path.resolve()), "record": index}
            try:
                if not isinstance(row, dict):
                    raise ValueError("History record must be an object")
                if not _successful(row):
                    raise ValueError("Not a completed successful answer")
                raw = row.get("problem_snapshot")
                if raw is None:
                    metadata = row.get("problem_metadata") or {}
                    if not isinstance(metadata, dict):
                        raise ValueError("Invalid legacy problem metadata")
                    fields = set(ProblemSnapshot.model_fields) - {"schema_version"}
                    merged = {**metadata, **row}
                    raw = {key: merged[key] for key in fields if key in merged}
                    logger.warning("legacy_example_metadata", **source)
                elif not isinstance(raw, dict) or "schema_version" not in raw:
                    raise ValueError("Missing problem snapshot version")
                snapshot = ProblemSnapshot.model_validate(raw)
                if snapshot.problem_id != row.get("problem_id"):
                    raise ValueError("Problem snapshot identity mismatch")
                examples.append(
                    SimilarProblem(
                        ExampleProblem(**snapshot.model_dump(exclude={"schema_version"})),
                        row["generated_code"],
                        0.0,
                        [],
                        sources=[source],
                    )
                )
            except (ValueError, TypeError, KeyError) as exc:
                logger.warning("historical_example_skipped", **source, reason=str(exc))
    return create_manifest(examples)
