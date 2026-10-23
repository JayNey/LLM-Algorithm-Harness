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
    temp_history_path.write_text("{ invalid json", encoding="utf-8")

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
    with open(temp_history_path, encoding="utf-8") as f:
        data = json.load(f)

    assert "runs" in data
    assert len(data["runs"]) == 1
    assert data["runs"][0]["run_id"] == "test_run_001"
    assert data["runs"][0]["strategy"] == "direct"
    assert data["runs"][0]["model"] == "claude-opus-5"


def test_save_preserves_history_before_lock(monkeypatch, temp_history_path, sample_run_record):
    from contextlib import contextmanager

    from src.incremental import history as history_mod

    history = IncrementalHistory([sample_run_record])
    history.save(temp_history_path)
    original = temp_history_path.read_bytes()
    real_lock = history_mod.exclusive_lock

    @contextmanager
    def checked_lock(file_obj):
        assert temp_history_path.read_bytes() == original
        assert file_obj.tell() == 0  # Windows locks relative to this position.
        with real_lock(file_obj):
            yield

    monkeypatch.setattr(history_mod, "exclusive_lock", checked_lock)
    history.save(temp_history_path)


def test_failed_save_lock_preserves_history(monkeypatch, temp_history_path, sample_run_record):
    from contextlib import contextmanager

    from src.incremental import history as history_mod

    IncrementalHistory([sample_run_record]).save(temp_history_path)
    original = temp_history_path.read_bytes()

    @contextmanager
    def busy_lock(file_obj):
        raise OSError("lock busy")
        yield

    monkeypatch.setattr(history_mod, "exclusive_lock", busy_lock)
    with pytest.raises(OSError, match="lock busy"):
        IncrementalHistory([]).save(temp_history_path)
    assert temp_history_path.read_bytes() == original


def test_save_flushes_before_unlock(monkeypatch, temp_history_path, sample_run_record):
    from contextlib import contextmanager

    from src.incremental import history as history_mod

    @contextmanager
    def checked_lock(file_obj):
        # Observe at unlock without native lock side effects (Windows seek flushes).
        yield
        data = json.loads(temp_history_path.read_text(encoding="utf-8"))
        assert data["runs"][0]["run_id"] == sample_run_record.run_id

    monkeypatch.setattr(history_mod, "exclusive_lock", checked_lock)
    IncrementalHistory([sample_run_record]).save(temp_history_path)


def test_save_shorter_history_removes_old_bytes(temp_history_path, sample_run_record):
    IncrementalHistory([sample_run_record]).save(temp_history_path)
    IncrementalHistory([]).save(temp_history_path)
    assert json.loads(temp_history_path.read_text(encoding="utf-8")) == {"runs": []}


def test_load_waits_for_writer(monkeypatch, temp_history_path, sample_run_record):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from src.incremental import history as history_mod
    from src.utils import file_lock

    if file_lock.fcntl is None:
        pytest.skip("requires blocking Unix flock")

    IncrementalHistory([sample_run_record]).save(temp_history_path)
    writing = Event()
    release_writer = Event()
    reading = Event()
    real_dump = history_mod.json.dump
    real_lock = history_mod.exclusive_lock

    def paused_dump(*args, **kwargs):
        writing.set()  # save has opened/truncated the file and owns the lock.
        assert release_writer.wait(5)
        return real_dump(*args, **kwargs)

    def observed_lock(file_obj):
        if not file_obj.writable():
            reading.set()
        return real_lock(file_obj)

    monkeypatch.setattr(history_mod.json, "dump", paused_dump)
    monkeypatch.setattr(history_mod, "exclusive_lock", observed_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        writer = pool.submit(IncrementalHistory([sample_run_record]).save, temp_history_path)
        try:
            assert writing.wait(5)
            reader = pool.submit(IncrementalHistory.load, temp_history_path)
            assert reading.wait(1), "load must acquire the history lock"
            assert not reader.done(), "load returned while the writer held its lock"
        finally:
            release_writer.set()
        writer.result(timeout=5)
        assert reader.result(timeout=5).runs == [sample_run_record]
