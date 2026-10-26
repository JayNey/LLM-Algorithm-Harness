"""End-to-end CLI subprocess tests for command handlers (coverage for src/main.py)."""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import pytest

from src.main import (
    run_benchmark_command,
    run_cache_command,
    run_import_command,
    run_tags_normalize_command,
)
from src.utils.encoding import utf8_subprocess_env

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    return subprocess.run(
        [sys.executable, "-m", "src.main", *argv],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
        env=utf8_subprocess_env(env),
        encoding="utf-8",
    )


def write_problems(tmp_path, count=3):
    problems = [
        {
            "problem_id": f"mock-{i}",
            "title": f"Mock Problem {i}",
            "description": "A generated problem description long enough.",
            "difficulty": "easy",
            "tags": ["mock"],
            "test_cases": [{"input": {"x": i}, "expected_output": i}],
        }
        for i in range(count)
    ]
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(problems), encoding="utf-8")
    return path


class TestImportCommand:
    def _args(self, tmp_path, **over):
        defaults = dict(
            source="mock",
            import_source=None,
            input="3",
            output=str(tmp_path / "imported.json"),
            preview=False,
            update_strategy="skip",
            force=True,
            strict=False,
            tags=None,
            contest=None,
            min_rating=None,
            max_rating=None,
            import_limit=None,
            release_version=None,
            start_date=None,
            end_date=None,
            import_difficulty=None,
            log_format="console",
        )
        defaults.update(over)
        return argparse.Namespace(**defaults)

    def test_mock_import_writes_dataset(self, tmp_path, capsys):
        args = self._args(tmp_path)
        assert run_import_command(args) == 0
        out = Path(args.output)
        data = json.loads(out.read_text(encoding="utf-8"))
        assert len(data) == 3
        assert "Import Summary:" in capsys.readouterr().out

    def test_import_unknown_source_errors(self, tmp_path, capsys):
        args = self._args(tmp_path, source="alien")
        assert run_import_command(args) == 2
        assert "--source is required" in capsys.readouterr().err

    def test_import_missing_input_errors(self, tmp_path, capsys):
        args = self._args(tmp_path, input=None)
        assert run_import_command(args) == 2
        assert "--input is required" in capsys.readouterr().err

    def test_import_preview_does_not_write(self, tmp_path, capsys):
        args = self._args(tmp_path, preview=True)
        assert run_import_command(args) == 0
        assert "[PREVIEW MODE]" in capsys.readouterr().out
        assert not Path(args.output).exists()

    def test_import_duplicate_skip_keeps_dataset_stable(self, tmp_path):
        args = self._args(tmp_path)
        run_import_command(args)
        before = json.loads(Path(args.output).read_text(encoding="utf-8"))
        assert run_import_command(args) == 0
        after = json.loads(Path(args.output).read_text(encoding="utf-8"))
        assert len(after) == len(before) == 3


class TestBenchmarkCommand:
    @pytest.fixture
    def benchmark_run(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "benchmark.json").write_text(
            json.dumps({"name": "历史基准", "problems": ["p1", "missing-p2"]}),
            encoding="utf-8",
        )
        (tmp_path / "config.yaml").write_text(
            json.dumps(
                {
                    "llm_config": {
                        "provider": "local",
                        "model": "org/test:model",
                        "api_key": "test-only-key",
                    },
                    "dataset_path": "problems.json",
                }
            ),
            encoding="utf-8",
        )
        results = {
            "suite": {"name": "历史基准", "version": "1.0", "frozen": True},
            "problems_evaluated": 1,
            "problems_missing": 1,
            "strategies": {
                "vanilla": {
                    "total": 1,
                    "passed": 1,
                    "failed": 0,
                    "accuracy": 1.0,
                    "avg_attempts": 1.0,
                    "total_tokens": 100,
                    "total_cost": 0.01,
                },
                "cot": {
                    "total": 1,
                    "passed": 0,
                    "failed": 1,
                    "accuracy": 0.0,
                    "avg_attempts": 2.0,
                    "total_tokens": 200,
                    "total_cost": 0.02,
                },
            },
            "accuracy": 0.5,
            "cost_usd": 0.03,
        }
        monkeypatch.setattr(
            "src.benchmark.executor.BenchmarkExecutor.execute", lambda self: results
        )
        args = argparse.Namespace(
            list_suites=False,
            suite="benchmark.json",
            compare=False,
            output=None,
            log_format="console",
        )
        return args, results

    def test_run_saves_complete_history(self, benchmark_run, tmp_path, capsys):
        from src.benchmark.history import BenchmarkHistoryStorage

        args, results = benchmark_run
        before = datetime.now()
        assert run_benchmark_command(args) == 0
        after = datetime.now()
        files = list((tmp_path / "results" / "benchmark").glob("*.json"))
        assert len(files) == 1
        saved = BenchmarkHistoryStorage().load_result(files[0])
        assert saved["suite_name"] == "历史基准"
        assert saved["model_id"] == "org/test:model"
        assert before <= datetime.fromisoformat(saved["timestamp"]) <= after
        assert saved["results"] == results
        assert "test-only-key" not in files[0].read_text(encoding="utf-8")
        assert str(files[0].relative_to(tmp_path)) in capsys.readouterr().out

    def test_failed_evaluation_does_not_create_history(
        self, benchmark_run, tmp_path, monkeypatch, capsys
    ):
        def fail(self):
            raise ValueError("evaluation failed")

        monkeypatch.setattr("src.benchmark.executor.BenchmarkExecutor.execute", fail)
        assert run_benchmark_command(benchmark_run[0]) == 1
        assert not (tmp_path / "results" / "benchmark").exists()
        assert "evaluation failed" in capsys.readouterr().err

    def test_history_directory_failure_returns_error(self, benchmark_run, tmp_path, capsys):
        (tmp_path / "results").mkdir()
        (tmp_path / "results" / "benchmark").write_text("blocked", encoding="utf-8")
        assert run_benchmark_command(benchmark_run[0]) == 1
        captured = capsys.readouterr()
        assert "Error:" in captured.err
        assert "Benchmark evaluation completed" not in captured.out

    def test_history_write_failure_returns_error(self, benchmark_run, monkeypatch, capsys):
        def fail(self, suite_name, model_id, results, timestamp=None):
            raise OSError("history disk full")

        monkeypatch.setattr("src.benchmark.history.BenchmarkHistoryStorage.save_result", fail)
        assert run_benchmark_command(benchmark_run[0]) == 1
        captured = capsys.readouterr()
        assert "history disk full" in captured.err
        assert "Benchmark evaluation completed" not in captured.out

    def test_list_suites_prints_files(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "benchmark.json").write_text(
            json.dumps({"name": "visible-suite", "problems": ["p1"]}),
            encoding="utf-8",
        )
        args = argparse.Namespace(
            list_suites=True, suite=None, compare=False, output=None, log_format="console"
        )
        assert run_benchmark_command(args) == 0
        assert "benchmark.json" in capsys.readouterr().out
        assert not (tmp_path / "results" / "benchmark").exists()

    def test_list_suites_empty_dir(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = argparse.Namespace(
            list_suites=True, suite=None, compare=False, output=None, log_format="console"
        )
        assert run_benchmark_command(args) == 0


class TestTagsCommand:
    def test_normalize_preview_writes_report(self, tmp_path, capsys):
        dataset = write_problems(tmp_path)
        args = argparse.Namespace(
            dataset=str(dataset),
            mapping=None,
            output=None,
            report=str(tmp_path / "tags-report.json"),
            apply_recommendations=None,
            min_confidence=0.6,
            log_format="console",
        )
        assert run_tags_normalize_command(args) == 0
        report = json.loads((tmp_path / "tags-report.json").read_text(encoding="utf-8"))
        assert report


class TestCacheCommand:
    def test_cache_stats(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = argparse.Namespace(cache_action="stats", model=None, log_format="console")
        assert run_cache_command(args) == 0
        assert "Total entries: 0" in capsys.readouterr().out

    def test_cache_clear(self, tmp_path, monkeypatch, capsys):
        monkeypatch.chdir(tmp_path)
        args = argparse.Namespace(cache_action="clear", model=None, log_format="console")
        assert run_cache_command(args) == 0
        assert "cleared" in capsys.readouterr().out.lower()


class TestSubprocessDispatch:
    def test_runs_dispatch_via_subprocess(self, tmp_path):
        """One subprocess smoke test proving the runs command is wired in the parser."""
        result = run_cli("runs", "list", "--output", str(tmp_path))
        assert result.returncode == 0


class TestImportConfirmation:
    def test_confirm_no_cancels_import(self, tmp_path, monkeypatch, capsys):
        args = argparse.Namespace(
            source="mock",
            import_source=None,
            input="2",
            output=str(tmp_path / "out.json"),
            preview=False,
            update_strategy="skip",
            force=False,
            strict=False,
            tags=None,
            contest=None,
            min_rating=None,
            max_rating=None,
            import_limit=None,
            release_version=None,
            start_date=None,
            end_date=None,
            import_difficulty=None,
            log_format="console",
        )
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        assert run_import_command(args) == 0
        assert "Import cancelled." in capsys.readouterr().out
        assert not Path(args.output).exists()

    def test_confirm_yes_persists_dataset(self, tmp_path, monkeypatch, capsys):
        args = argparse.Namespace(
            source="mock",
            import_source=None,
            input="2",
            output=str(tmp_path / "out.json"),
            preview=False,
            update_strategy="skip",
            force=False,
            strict=False,
            tags=None,
            contest=None,
            min_rating=None,
            max_rating=None,
            import_limit=None,
            release_version=None,
            start_date=None,
            end_date=None,
            import_difficulty=None,
            log_format="console",
        )
        monkeypatch.setattr("builtins.input", lambda prompt="": "y")
        assert run_import_command(args) == 0
        assert "Dataset written to:" in capsys.readouterr().out
        assert Path(args.output).exists()
