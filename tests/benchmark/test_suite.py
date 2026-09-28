"""Tests for benchmark suite management."""

import json
import tempfile
from pathlib import Path

import pytest

from src.benchmark.suite import BenchmarkSuite, load_benchmark_suite


def test_benchmark_suite_creation():
    """Test creating a BenchmarkSuite instance."""
    suite = BenchmarkSuite(
        name="Test Suite",
        problems=["problem1", "problem2"],
        frozen=True,
        version="1.0",
    )

    assert suite.name == "Test Suite"
    assert len(suite.problems) == 2
    assert suite.frozen is True
    assert suite.version == "1.0"


def test_benchmark_suite_validation():
    """Test BenchmarkSuite validation."""
    # Empty problems list should fail
    with pytest.raises(ValueError):
        BenchmarkSuite(name="Test", problems=[], frozen=True)

    # Empty name should fail
    with pytest.raises(ValueError):
        BenchmarkSuite(name="", problems=["p1"], frozen=True)


def test_load_benchmark_suite():
    """Test loading benchmark suite from file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(
            {
                "name": "Test Suite",
                "problems": ["p1", "p2"],
                "frozen": True,
                "version": "1.0",
            },
            f,
        )
        temp_file = f.name

    try:
        suite = load_benchmark_suite(temp_file)
        assert suite.name == "Test Suite"
        assert len(suite.problems) == 2
    finally:
        Path(temp_file).unlink()


def test_load_invalid_json():
    """Test loading invalid JSON file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{invalid json")
        temp_file = f.name

    try:
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_benchmark_suite(temp_file)
    finally:
        Path(temp_file).unlink()


def test_load_nonexistent_file():
    """Test loading non-existent file."""
    with pytest.raises(FileNotFoundError):
        load_benchmark_suite("nonexistent.json")
