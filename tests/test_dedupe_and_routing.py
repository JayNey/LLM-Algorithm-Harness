"""Tests for the problems deduplicate command and main() CLI routing."""

import argparse
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.main import main, run_problems_deduplicate_command


def problem(id_, title="A title", description="A description body for the problem."):
    return {
        "problem_id": id_,
        "title": title,
        "description": description,
        "difficulty": "easy",
        "tags": ["tag"],
        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
    }


def make_args(tmp_path, **over):
    defaults = dict(
        dataset=str(tmp_path / "problems.json"),
        threshold=0.8,
        dry_run=False,
        auto_merge=True,
    )
    defaults.update(over)
    return argparse.Namespace(**defaults)


def write_dataset(tmp_path, problems):
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(problems), encoding="utf-8")
    return path


class TestProblemsDeduplicateCommand:
    def test_deduplicates_fingerprint_duplicates_auto_merge(self, tmp_path, capsys):
        dataset = write_dataset(
            tmp_path,
            [problem("p1"), problem("p1"), problem("p2", title="Different problem title")],
        )
        assert run_problems_deduplicate_command(make_args(tmp_path)) == 0

        final = json.loads(dataset.read_text(encoding="utf-8"))
        ids = [item["problem_id"] for item in final]
        assert ids.count("p1") == 1
        assert "p2" in ids
        assert "Dataset updated" in capsys.readouterr().out

    def test_dry_run_does_not_write(self, tmp_path):
        dataset = write_dataset(tmp_path, [problem("p1"), problem("p1")])
        before = dataset.read_text(encoding="utf-8")

        assert run_problems_deduplicate_command(make_args(tmp_path, dry_run=True)) == 0
        assert dataset.read_text(encoding="utf-8") == before

    def test_interactive_reject_keeps_duplicates(self, tmp_path, monkeypatch):
        dataset = write_dataset(tmp_path, [problem("p1"), problem("p1")])
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")

        assert run_problems_deduplicate_command(make_args(tmp_path, auto_merge=False)) == 0
        final = json.loads(dataset.read_text(encoding="utf-8"))
        assert len(final) == 2

    def test_missing_dataset_errors(self, tmp_path, capsys):
        assert run_problems_deduplicate_command(make_args(tmp_path)) == 1
        assert "Dataset not found" in capsys.readouterr().err

    def test_non_list_dataset_errors(self, tmp_path):
        path = tmp_path / "problems.json"
        path.write_text(json.dumps({"not": "a list"}), encoding="utf-8")
        assert run_problems_deduplicate_command(make_args(tmp_path)) == 1

    def test_clean_dataset_reports_no_duplicates(self, tmp_path):
        dataset = write_dataset(tmp_path, [problem("p1"), problem("p2", title="Other")])
        assert run_problems_deduplicate_command(make_args(tmp_path, dry_run=True)) == 0
        assert json.loads(dataset.read_text(encoding="utf-8"))[0]["problem_id"] == "p1"


class TestMainRouting:
    """Cover the main() subcommand dispatch arms with mocked handlers."""

    @pytest.mark.parametrize(
        "argv",
        [
            ["experiment", "--config", "cfg.json"],
            ["optimize", "--experiment", "results/experiments/exp-1"],
            ["recalibrate", "--history", "results", "--output", "out.json"],
            ["runs", "list"],
            ["ab-test", "--config", "ab.json"],
            ["benchmark", "--list-suites"],
            ["tags", "normalize", "--dataset", "problems.json"],
            ["cache", "stats"],
            ["problems", "deduplicate", "--dataset", "problems.json"],
        ],
    )
    def test_dispatch_reaches_handler(self, argv, monkeypatch, capsys):
        handler_name = {
            "experiment": "run_experiment_command",
            "optimize": "run_optimize_command",
            "recalibrate": "run_recalibrate_command",
            "runs": "run_runs_command",
            "ab-test": "run_ab_test_command",
            "benchmark": "run_benchmark_command",
            "tags": "run_tags_normalize_command",
            "cache": "run_cache_command",
            "problems": "run_problems_deduplicate_command",
        }[argv[0]]
        mock_handler = MagicMock(return_value=0)
        monkeypatch.setattr(f"src.main.{handler_name}", mock_handler)
        monkeypatch.setattr("sys.argv", ["harness", *argv])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_handler.assert_called_once()
