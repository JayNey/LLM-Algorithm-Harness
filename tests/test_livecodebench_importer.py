"""Tests for safe, versioned LiveCodeBench importing."""

import json
from pathlib import Path

import pytest

from src.importers.livecodebench import LiveCodeBenchImporter


FIXTURE = Path(__file__).parent / "fixtures" / "livecodebench.json"


def test_import_maps_public_and_hidden_protocols_and_records_version():
    importer = LiveCodeBenchImporter(release_version="release_v6")
    raw = importer.fetch_problems(str(FIXTURE))
    problems = importer.transform_to_schema(raw)

    assert [problem.problem_id for problem in problems] == ["livecodebench-cf-001", "livecodebench-lc-002", "livecodebench-ac-003"]
    assert problems[0].input_output_mode == "stdin_stdout"
    assert len(problems[0].public_test_cases) == 1
    assert len(problems[0].hidden_test_cases) == 1
    assert problems[0].source_version == "release_v6"
    assert problems[0].source_metadata["contest_date"].startswith("2024-01-15")


def test_import_rejects_unsafe_private_payload_without_deserializing():
    importer = LiveCodeBenchImporter()
    problem = importer.transform_to_schema(importer.fetch_problems(str(FIXTURE)))[2]

    assert problem.hidden_test_cases == []
    assert problem.needs_manual_completion is True
    assert any("pickle" in note for note in problem.manual_completion_notes)


def test_filters_are_reproducible_and_recorded():
    importer = LiveCodeBenchImporter(
        release_version="release_v6", start_date="2024-02-01", difficulty="hard", limit=1
    )
    problems = importer.transform_to_schema(importer.fetch_problems(str(FIXTURE)))

    assert [problem.problem_id for problem in problems] == ["livecodebench-lc-002"]
    report = importer.generate_report(type("Result", (), {
        "total_attempted": 1,
        "successful": problems,
        "failed": [],
        "duplicates_skipped": [],
        "duplicates_overwritten": [],
        "warnings": [],
    })(), str(FIXTURE), "out.json", True)
    assert report["release_version"] == "release_v6"
    assert report["selected_problem_ids"] == ["livecodebench-lc-002"]
    assert report["source_sha256"]


def test_jsonl_cache_is_supported(tmp_path):
    records = json.loads(FIXTURE.read_text(encoding="utf-8"))[:1]
    path = tmp_path / "cache.jsonl"
    path.write_text("\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8")

    problems = LiveCodeBenchImporter().transform_to_schema(
        LiveCodeBenchImporter().fetch_problems(str(path))
    )
    assert len(problems) == 1


def test_unknown_release_is_rejected():
    with pytest.raises(ValueError, match="Unsupported LiveCodeBench release"):
        LiveCodeBenchImporter(release_version="release_latest")
