"""Tests for incremental history management."""

import json
from datetime import datetime, timezone

import pytest

from src.incremental.history import IncrementalHistory, RunRecord


@pytest.fixture
def temp_history_path(tmp_path):
    """Create a temporary path for history files."""
    return tmp_path / "history.json"


@pytest.fixture
def sample_run_record():
    """Create a sample run record."""
    return RunRecord(
        run_id="test_run_001",
        timestamp=datetime.now(timezone.utc).isoformat(),
        strategy="direct",
        model="claude-opus-5",
        dataset_fingerprint={"prob1": "abc123", "prob2": "def456"},
        result_path="/path/to/results",
        problem_count=2,
        success_count=1,
    )


def test_incremental_history_init():
    """Test IncrementalHistory initialization."""
    history = IncrementalHistory(runs=[])
    assert history.runs == []


def test_add_run(sample_run_record):
    """Test adding a run record."""
    history = IncrementalHistory(runs=[])
    history.add_run(sample_run_record)

    assert len(history.runs) == 1
    assert history.runs[0] == sample_run_record


def test_save_and_load(temp_history_path, sample_run_record):
    """Test saving and loading history."""
    # Create and save history
    history = IncrementalHistory(runs=[])
    history.add_run(sample_run_record)
    history.save(temp_history_path)

    # Verify file exists
    assert temp_history_path.exists()

    # Load and verify
    loaded_history = IncrementalHistory.load(temp_history_path)
    assert len(loaded_history.runs) == 1
    assert loaded_history.runs[0].run_id == sample_run_record.run_id
    assert loaded_history.runs[0].strategy == sample_run_record.strategy


def test_load_nonexistent_file(temp_history_path):
    """Test loading from a nonexistent file returns empty history."""
    history = IncrementalHistory.load(temp_history_path)
    assert history.runs == []


def test_load_corrupted_file(temp_history_path):
    """Test loading corrupted JSON returns empty history."""
    # Write invalid JSON
    temp_history_path.write_text("{ invalid json")

    history = IncrementalHistory.load(temp_history_path)
    assert history.runs == []


def test_save_creates_parent_directories(tmp_path):
    """Test that save creates parent directories."""
    nested_path = tmp_path / "nested" / "dir" / "history.json"
    history = IncrementalHistory(runs=[])
    history.save(nested_path)

    assert nested_path.exists()
    assert nested_path.parent.exists()


def test_multiple_runs(temp_history_path):
    """Test saving and loading multiple runs."""
    history = IncrementalHistory(runs=[])

    # Add multiple runs
    for i in range(3):
        record = RunRecord(
            run_id=f"run_{i}",
            timestamp=datetime.now(timezone.utc).isoformat(),
            strategy="direct",
            model="claude-opus-5",
            dataset_fingerprint={"prob1": f"hash_{i}"},
            result_path=f"/path/to/run_{i}",
            problem_count=1,
            success_count=0,
        )
        history.add_run(record)

    history.save(temp_history_path)

    # Load and verify
    loaded = IncrementalHistory.load(temp_history_path)
    assert len(loaded.runs) == 3
    assert [r.run_id for r in loaded.runs] == ["run_0", "run_1", "run_2"]


def test_history_json_format(temp_history_path, sample_run_record):
    """Test that saved JSON has the correct format."""
    history = IncrementalHistory(runs=[])
    history.add_run(sample_run_record)
    history.save(temp_history_path)

    # Read and parse JSON
    with open(temp_history_path) as f:
        data = json.load(f)

    assert "runs" in data
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == "test_run_001"
    assert data["runs"][0]["strategy"] == "direct"
    assert data["runs"][0]["model"] == "claude-opus-5"
