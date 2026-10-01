"""End-to-end CLI subprocess tests for command handlers (coverage for src/main.py)."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from src.main import (
    run_benchmark_command,
    run_cache_command,
    run_import_command,
    run_tags_normalize_command,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_cli(*argv, cwd=None):
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT))
    return subprocess.run(
        [sys.executable, "-m", "src.main", *argv],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=cwd,
        env=env,
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
