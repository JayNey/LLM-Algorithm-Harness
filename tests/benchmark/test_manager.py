"""Tests for benchmark suite loading and manager."""

import json
from pathlib import Path

import pytest

from src.benchmark.manager import BenchmarkManager
from src.benchmark.suite import load_benchmark_suite


def write_config(path: Path, payload):
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def valid_payload(name="suite-a", problems=None):
    if problems is None:
        problems = ["p1", "p2"]
    return {
        "name": name,
        "problems": problems,
        "version": "2.0",
        "description": "test suite",
    }


class TestLoadBenchmarkSuite:
    def test_loads_valid_config(self, tmp_path):
        path = write_config(tmp_path / "benchmark.json", valid_payload())
        suite = load_benchmark_suite(path)
        assert suite.name == "suite-a"
        assert suite.problems == ["p1", "p2"]
        assert suite.version == "2.0"
        assert suite.frozen is True
        assert suite.description == "test suite"

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_benchmark_suite(tmp_path / "nope.json")

    def test_invalid_json_raises_value_error(self, tmp_path):
        path = tmp_path / "benchmark.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(ValueError, match="Invalid JSON"):
            load_benchmark_suite(path)

    def test_empty_problems_rejected(self, tmp_path):
        path = write_config(tmp_path / "benchmark.json", valid_payload(problems=[]))
        with pytest.raises(ValueError, match="at least 1 item"):
            load_benchmark_suite(path)

    def test_blank_name_rejected(self, tmp_path):
        path = write_config(tmp_path / "benchmark.json", valid_payload(name="   "))
        with pytest.raises(ValueError, match="cannot be empty"):
            load_benchmark_suite(path)

    def test_name_is_stripped(self, tmp_path):
        path = write_config(tmp_path / "benchmark.json", valid_payload(name="  suite-x  "))
        assert load_benchmark_suite(path).name == "suite-x"


class TestBenchmarkManager:
    def test_load_and_get_suite(self, tmp_path):
        write_config(tmp_path / "benchmark.json", valid_payload())
        manager = BenchmarkManager(tmp_path)
        suite = manager.load_suite(tmp_path / "benchmark.json")
        assert manager.get_suite("suite-a") is suite
        assert manager.get_suite("missing") is None

    def test_missing_config_raises_and_logs(self, tmp_path):
        manager = BenchmarkManager(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.load_suite(tmp_path / "nope.json")

    def test_list_suites_finds_benchmark_files(self, tmp_path):
        write_config(tmp_path / "benchmark.json", valid_payload(name="a"))
        write_config(tmp_path / "benchmark.algo.json", valid_payload(name="b"))
        write_config(tmp_path / "other.json", valid_payload(name="c"))
        manager = BenchmarkManager(tmp_path)
        listed = manager.list_suites()
        assert len(listed) == 2
        assert all("benchmark" in Path(p).name for p in listed)

    def test_load_all_suites_skips_invalid(self, tmp_path):
        write_config(tmp_path / "benchmark.json", valid_payload(name="good"))
        (tmp_path / "benchmark.bad.json").write_text("{bad", encoding="utf-8")
        manager = BenchmarkManager(tmp_path)
        loaded = manager.load_all_suites()
        assert set(loaded) == {"good"}
