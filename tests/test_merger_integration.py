"""Integration tests for merger functions that interact with file system."""

import json
from pathlib import Path

import pytest

from src.incremental.history import IncrementalHistory
from src.incremental.merger import (
    load_historical_results_from_summary,
    update_incremental_history,
)
from src.models import ExecutionResult


@pytest.fixture
def temp_results_dir(tmp_path):
    """Create a temporary results directory with summary and result files."""
    results_dir = tmp_path / "results"
    results_dir.mkdir()

    # Create summary.json
    summary = {
        "strategies": {
            "vanilla": {"total": 2, "passed": 1},
            "chain-of-thought": {"total": 2, "passed": 2},
        }
    }
    with open(results_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f)

    # Create vanilla_results.json
    vanilla_results = [
        {
            "problem_id": "prob1",
            "strategy": "vanilla",
            "generated_code": "print('hello')",
            "status": "success",
            "passed": True,
            "execution_time": 1.5,
            "error": None,
            "metadata": {},
        },
        {
            "problem_id": "prob2",
            "strategy": "vanilla",
            "generated_code": "print('world')",
            "status": "failed",
            "passed": False,
            "execution_time": 2.0,
            "error": "AssertionError",
            "metadata": {},
        },
    ]
    with open(results_dir / "vanilla_results.json", "w", encoding="utf-8") as f:
        json.dump(vanilla_results, f)

    # Create chain-of-thought_results.json
    cot_results = [
        {
            "problem_id": "prob1",
            "strategy": "chain-of-thought",
            "generated_code": "# thinking\nprint('hello')",
            "status": "success",
            "passed": True,
            "execution_time": 2.5,
            "error": None,
            "metadata": {},
        },
        {
            "problem_id": "prob3",
            "strategy": "chain-of-thought",
            "generated_code": "# more thinking\nprint('test')",
            "status": "success",
            "passed": True,
            "execution_time": 3.0,
            "error": None,
            "metadata": {},
        },
    ]
    with open(results_dir / "chain-of-thought_results.json", "w", encoding="utf-8") as f:
        json.dump(cot_results, f)

    return results_dir


def test_load_historical_results_from_summary(temp_results_dir):
    """Test loading historical results from summary.json structure."""
    problem_ids = {"prob1", "prob2"}

    results = load_historical_results_from_summary(temp_results_dir, problem_ids)

    assert "vanilla" in results
    assert "chain-of-thought" in results

    # Check vanilla results
    assert len(results["vanilla"]) == 2
    assert all(isinstance(r, ExecutionResult) for r in results["vanilla"])
    assert {r.problem_id for r in results["vanilla"]} == {"prob1", "prob2"}

    # Check chain-of-thought results (only prob1 should be loaded)
    assert len(results["chain-of-thought"]) == 1
    assert results["chain-of-thought"][0].problem_id == "prob1"


def test_load_historical_results_from_summary_missing_file(tmp_path):
    """Test loading from non-existent summary file."""
    results = load_historical_results_from_summary(tmp_path / "nonexistent", {"prob1"})
    assert results == {}


def test_load_historical_results_from_summary_corrupted_json(tmp_path):
    """Test loading from corrupted summary file."""
    summary_path = tmp_path / "summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("{ invalid json")

    results = load_historical_results_from_summary(tmp_path, {"prob1"})
    assert results == {}


def test_load_historical_results_from_summary_missing_strategy_file(temp_results_dir):
    """Test when strategy is in summary but results file is missing."""
    # Remove one results file
    (temp_results_dir / "vanilla_results.json").unlink()

    problem_ids = {"prob1", "prob2"}
    results = load_historical_results_from_summary(temp_results_dir, problem_ids)

    # Should still load chain-of-thought results
    assert "chain-of-thought" in results
    # vanilla should not be in results since file is missing
    assert "vanilla" not in results


def test_update_incremental_history(tmp_path):
    """Test updating incremental history with a new run."""
    history = IncrementalHistory(runs=[])
    history_path = tmp_path / "history.json"

    dataset_fingerprint = {"prob1": "hash1", "prob2": "hash2"}

    update_incremental_history(
        history=history,
        history_path=history_path,
        dataset_fingerprint=dataset_fingerprint,
        result_path="results/run_20240101_120000/summary.json",
        strategy="vanilla",
        model="gpt-4",
        problem_count=2,
        success_count=1,
    )

    # Verify history was updated
    assert len(history.runs) == 1
    run = history.runs[0]
    assert run.strategy == "vanilla"
    assert run.model == "gpt-4"
    assert run.dataset_fingerprint == dataset_fingerprint
    assert run.problem_count == 2
    assert run.success_count == 1
    assert run.run_id == "run_20240101_120000"

    # Verify history was saved
    assert history_path.exists()
    loaded_history = IncrementalHistory.load(history_path)
    assert len(loaded_history.runs) == 1
    assert loaded_history.runs[0].strategy == "vanilla"


def test_update_incremental_history_multiple_runs(tmp_path):
    """Test updating history with multiple runs."""
    history = IncrementalHistory(runs=[])
    history_path = tmp_path / "history.json"

    # Add first run
    update_incremental_history(
        history=history,
        history_path=history_path,
        dataset_fingerprint={"prob1": "hash1"},
        result_path="results/run1/summary.json",
        strategy="vanilla",
        model="gpt-4",
        problem_count=1,
        success_count=1,
    )

    # Add second run
    update_incremental_history(
        history=history,
        history_path=history_path,
        dataset_fingerprint={"prob1": "hash1", "prob2": "hash2"},
        result_path="results/run2/summary.json",
        strategy="vanilla",
        model="gpt-4",
        problem_count=2,
        success_count=2,
    )

    # Verify both runs are in history
    assert len(history.runs) == 2
    assert history.runs[0].problem_count == 1
    assert history.runs[1].problem_count == 2

    # Verify persistence
    loaded_history = IncrementalHistory.load(history_path)
    assert len(loaded_history.runs) == 2
