"""Tests for change detection and matching logic."""

import json
from datetime import datetime, timezone

import pytest

from src.incremental.detector import (
    detect_changes,
    find_matching_run,
    load_historical_results,
    should_use_incremental,
)
from src.incremental.history import IncrementalHistory, RunRecord


@pytest.fixture
def base_fingerprint():
    """Create a base dataset fingerprint."""
    return {
        "prob1": "hash1",
        "prob2": "hash2",
        "prob3": "hash3",
    }


def test_detect_changes_no_changes(base_fingerprint):
    """Test detecting no changes."""
    added, modified, removed = detect_changes(base_fingerprint, base_fingerprint)

    assert len(added) == 0
    assert len(modified) == 0
    assert len(removed) == 0


def test_detect_changes_added_problems(base_fingerprint):
    """Test detecting added problems."""
    current = {**base_fingerprint, "prob4": "hash4"}

    added, modified, removed = detect_changes(current, base_fingerprint)

    assert added == {"prob4"}
    assert len(modified) == 0
    assert len(removed) == 0


def test_detect_changes_modified_problems(base_fingerprint):
    """Test detecting modified problems."""
    current = {**base_fingerprint}
    current["prob2"] = "hash2_modified"

    added, modified, removed = detect_changes(current, base_fingerprint)

    assert len(added) == 0
    assert modified == {"prob2"}
    assert len(removed) == 0


def test_detect_changes_removed_problems(base_fingerprint):
    """Test detecting removed problems."""
    current = {"prob1": "hash1", "prob2": "hash2"}

    added, modified, removed = detect_changes(current, base_fingerprint)

    assert len(added) == 0
    assert len(modified) == 0
    assert removed == {"prob3"}


def test_detect_changes_multiple_types(base_fingerprint):
    """Test detecting multiple types of changes."""
    current = {
        "prob1": "hash1",  # unchanged
        "prob2": "hash2_modified",  # modified
        "prob4": "hash4",  # added
    }

    added, modified, removed = detect_changes(current, base_fingerprint)

    assert added == {"prob4"}
    assert modified == {"prob2"}
    assert removed == {"prob3"}


def test_should_use_incremental_small_changes():
    """Test incremental mode enabled for small changes."""
    changes = ({"new1"}, {"mod1"}, set())
    fingerprint = {"p1": "h", "p2": "h", "p3": "h", "p4": "h", "p5": "h"}
    assert should_use_incremental(changes, fingerprint) is True


def test_should_use_incremental_no_changes():
    """Test incremental mode disabled when no changes."""
    changes = (set(), set(), set())
    assert should_use_incremental(changes) is False


def test_should_use_incremental_large_changes():
    """Test incremental mode disabled when nothing is left to reuse."""
    # Simulate 8 added out of 8 total (100% changed, nothing reusable)
    added = {f"prob{i}" for i in range(8)}
    modified = set()
    removed = set()

    changes = (added, modified, removed)
    fingerprint = {f"prob{i}": "h" for i in range(8)}
    assert should_use_incremental(changes, fingerprint) is False


def test_find_matching_run_no_history():
    """Test finding matching run with empty history."""
    history = IncrementalHistory(runs=[])
    fingerprint = {"prob1": "hash1"}

    result = find_matching_run(history, fingerprint, "direct", "claude-opus-5")
    assert result is None


def test_find_matching_run_exact_match():
    """Test finding an exact matching run."""
    fingerprint = {"prob1": "hash1", "prob2": "hash2"}

    history = IncrementalHistory(runs=[])
    history.add_run(
        RunRecord(
            run_id="run1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            strategy="direct",
            model="claude-opus-5",
            dataset_fingerprint=fingerprint,
            result_path="/path/to/run1",
            problem_count=2,
            success_count=0,
        )
    )

    result = find_matching_run(history, fingerprint, "direct", "claude-opus-5")
    assert result is not None
    assert result.run_id == "run1"


def test_find_matching_run_strategy_mismatch():
    """Test that strategy must match."""
    fingerprint = {"prob1": "hash1"}

    history = IncrementalHistory(runs=[])
    history.add_run(
        RunRecord(
            run_id="run1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            strategy="cot",
            model="claude-opus-5",
            dataset_fingerprint=fingerprint,
            result_path="/path/to/run1",
            problem_count=1,
            success_count=0,
        )
    )

    result = find_matching_run(history, fingerprint, "direct", "claude-opus-5")
    assert result is None


def test_find_matching_run_model_mismatch():
    """Test that model must match."""
    fingerprint = {"prob1": "hash1"}

    history = IncrementalHistory(runs=[])
    history.add_run(
        RunRecord(
            run_id="run1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            strategy="direct",
            model="claude-sonnet-5",
            dataset_fingerprint=fingerprint,
            result_path="/path/to/run1",
            problem_count=1,
            success_count=0,
        )
    )

    result = find_matching_run(history, fingerprint, "direct", "claude-opus-5")
    assert result is None


def test_find_matching_run_most_recent():
    """Test that most recent matching run is returned."""
    fingerprint = {"prob1": "hash1"}

    history = IncrementalHistory(runs=[])
    # Add older run
    history.add_run(
        RunRecord(
            run_id="run1",
            timestamp="2024-01-01T00:00:00Z",
            strategy="direct",
            model="claude-opus-5",
            dataset_fingerprint=fingerprint,
            result_path="/path/to/run1",
            problem_count=1,
            success_count=0,
        )
    )
    # Add newer run
    history.add_run(
        RunRecord(
            run_id="run2",
            timestamp="2024-12-01T00:00:00Z",
            strategy="direct",
            model="claude-opus-5",
            dataset_fingerprint=fingerprint,
            result_path="/path/to/run2",
            problem_count=1,
            success_count=0,
        )
    )

    result = find_matching_run(history, fingerprint, "direct", "claude-opus-5")
    assert result is not None
    assert result.run_id == "run2"


def test_load_historical_results_missing_file(tmp_path):
    """Test loading results from missing file."""
    result_path = tmp_path / "nonexistent.json"
    results = load_historical_results(result_path, {"prob1", "prob2"})

    assert results == {}


def test_load_historical_results_corrupted_file(tmp_path):
    """Test loading results from corrupted JSON."""
    result_path = tmp_path / "results.json"
    result_path.write_text("{ invalid json", encoding="utf-8")

    results = load_historical_results(result_path, {"prob1"})
    assert results == {}


def test_load_historical_results_valid_file(tmp_path):
    """Test loading valid historical results from a run directory."""
    result_path = tmp_path / "run"
    result_path.mkdir()

    # Create mock results (one strategy's results file: a flat list)
    MOCK_DATA = [
        {
            "problem_id": "prob1",
            "strategy": "direct",
            "generated_code": "def solution(): pass",
            "status": "success",
            "execution_time": 1.5,
            "cost": 0.01,
        },
        {
            "problem_id": "prob2",
            "strategy": "direct",
            "generated_code": "def solution(): pass",
            "status": "failure",
            "execution_time": 2.0,
            "cost": 0.02,
        },
        {
            "problem_id": "prob3",
            "strategy": "direct",
            "generated_code": "def solution(): pass",
            "status": "success",
            "execution_time": 1.0,
            "cost": 0.01,
        },
    ]

    # Per-strategy result files, as written by save_results.
    (result_path / "direct_results.json").write_text(json.dumps(MOCK_DATA), encoding="utf-8")

    # Load only prob1 and prob3
    results = load_historical_results(result_path, {"prob1", "prob3"})

    assert "direct" in results
    assert len(results["direct"]) == 2
    assert results["direct"][0].problem_id == "prob1"
    assert results["direct"][0].status == "success"
    assert results["direct"][0].source == "reused"
    assert results["direct"][1].problem_id == "prob3"


def test_load_historical_results_multi_strategy_dir(tmp_path):
    """All per-strategy files in the run directory are loaded."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "vanilla_results.json").write_text(
        json.dumps(
            [{"problem_id": "p1", "strategy": "vanilla", "generated_code": "", "status": "success"}]
        ),
        encoding="utf-8",
    )
    (run_dir / "cot_results.json").write_text(
        json.dumps(
            [{"problem_id": "p1", "strategy": "cot", "generated_code": "", "status": "success"}]
        ),
        encoding="utf-8",
    )
    results = load_historical_results(run_dir, {"p1"})
    assert set(results) == {"vanilla", "cot"}


def test_load_historical_results_single_corrupt_file_disables_reuse(tmp_path):
    """One unreadable strategy file disables reuse entirely (all-or-nothing)."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "vanilla_results.json").write_text(
        json.dumps([{"problem_id": "p1", "strategy": "vanilla", "status": "success"}]),
        encoding="utf-8",
    )
    (run_dir / "cot_results.json").write_text("{corrupted", encoding="utf-8")
    assert load_historical_results(run_dir, {"p1"}) == {}


def test_should_use_incremental_threshold_requires_reusable_problems():
    """Incremental only pays off when at least one unchanged problem exists."""
    from src.incremental.detector import should_use_incremental

    everything_changed = ({"n1", "n2"}, {"m1"}, set())
    assert should_use_incremental(everything_changed, {"n1": "h", "n2": "h", "m1": "h"}) is False
    partial = ({"n1"}, {"m1"}, set())
    assert should_use_incremental(partial, {f"p{i}": "h" for i in range(5)}) is True
    assert should_use_incremental((set(), set(), set()), {"p1": "h"}) is False
