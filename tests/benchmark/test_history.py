"""Tests for benchmark history storage."""

import json
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from src.benchmark.history import BenchmarkHistoryStorage


@pytest.fixture
def temp_storage():
    """Create a temporary storage directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield BenchmarkHistoryStorage(tmpdir)


def test_save_and_load_result(temp_storage):
    """Test saving and loading benchmark results."""
    results = {
        "suite": {"name": "Test", "version": "1.0"},
        "problems_evaluated": 5,
        "strategies": {"vanilla": {"accuracy": 0.8}},
    }

    filepath = temp_storage.save_result("Test Suite", "gpt-4", results)
    assert filepath.exists()

    loaded = temp_storage.load_result(filepath)
    assert loaded["model_id"] == "gpt-4"
    assert loaded["suite_name"] == "Test Suite"


def test_list_results(temp_storage):
    """Test listing and filtering results."""
    results = {
        "suite": {"name": "Test", "version": "1.0"},
        "problems_evaluated": 5,
        "strategies": {"vanilla": {"accuracy": 0.8}},
    }

    temp_storage.save_result("Test Suite", "gpt-4", results)
    temp_storage.save_result("Test Suite", "gpt-3.5", results)

    all_results = temp_storage.list_results()
    assert len(all_results) == 2

    filtered = temp_storage.list_results(model_id="gpt-4")
    assert len(filtered) == 1
    assert filtered[0]["model_id"] == "gpt-4"
