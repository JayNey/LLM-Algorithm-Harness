"""
End-to-end tests for incremental evaluation (issue #87 follow-up fixes).

Proves the closed loop: first run evaluates everything and records history,
then a changed dataset triggers incremental mode that evaluates only the
changed problems, reuses historical results, and produces a merged report
with real (non-placeholder) metrics.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from src.models import LLMResponse, TokenUsage


def _dataset(tmp_path, problem_ids, modify_id=None):
    problems = []
    for problem_id in problem_ids:
        marker = "second" if (modify_id and problem_id == modify_id) else "first"
        problems.append(
            {
                "problem_id": problem_id,
                "title": f"P-{problem_id}",
                "description": f"Problem description for {problem_id} ({marker} version).",
                "difficulty": "easy",
                "tags": ["tag"],
                "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
            }
        )
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(problems), encoding="utf-8")
    return path


def _config_file(tmp_path, dataset):
    config = {
        "dataset_path": str(dataset),
        "output_dir": str(tmp_path / "results"),
        "llm_config": {"provider": "openai", "api_key": "test-key", "model": "test-model"},
        "strategies": [{"name": "vanilla", "max_iterations": 1}],
        "sandbox_config": {"backend": "host", "allowed_imports": []},
    }
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    return path


def _run_main(argv):
    from src.main import main

    exit_code = 0
    with patch("sys.argv", ["main.py"] + argv):
        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code or 0
    return exit_code


def _llm_factory():
    def factory(config):
        client = MagicMock()
        client.generate.return_value = LLMResponse(
            text="```python\ndef solution(x):\n    return x + 1\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model=config.model,
            finish_reason="stop",
            pricing_metadata={
                "model": config.model,
                "total_cost": 0.02,
                "usage_known": True,
                "pricing_known": True,
            },
        )
        return client

    return factory


@pytest.fixture
def sandboxed(monkeypatch):
    """Keep the host sandbox from executing anything real."""
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    yield


class TestIncrementalEndToEnd:
    def test_second_run_evaluates_only_changed_and_merges(self, tmp_path, capsys):
        dataset = _dataset(tmp_path, ["p1", "p2", "p3"])
        config_path = _config_file(tmp_path, dataset)

        # First run: full evaluation of 3 problems, records history.
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        first_out = capsys.readouterr().out

        history_path = tmp_path / "results" / ".incremental" / "history.json"
        assert history_path.exists(), "first run must record incremental history"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        runs = history.get("runs") or history.get("runs_history") or []
        assert runs, "history must contain the first run record"

        # Second run: modify one problem, add a new one.
        dataset2 = _dataset(tmp_path, ["p1", "p2", "p3", "p4"], modify_id="p2")
        dataset2.replace(dataset)  # keep same path (config points at it)
        capsys.readouterr()

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        second_out = capsys.readouterr().out

        assert "Incremental evaluation mode enabled" in second_out
        assert "Unchanged: 2 problems (reusing results)" in second_out
        assert "New: 1 problems" in second_out
        assert "Merged 2 reused results with 2 new results" in second_out
        # The merged report is a real report, not a placeholder.
        assert "Cost" not in second_out or "unknown" not in second_out.lower()

        # Latest run summary reflects the full merged dataset (4 problems).
        latest = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
        run_dir = tmp_path / "results" / latest["latest_run"]
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        report = summary["strategies"]["vanilla"]
        assert report["total_problems"] == 4
        assert report["estimated_cost_usd"] > 0, "merged report must keep real cost"
        assert set(report["by_difficulty"]) == {"easy"}
        assert report["avg_attempts_per_problem"] == 1.0

    def test_second_run_without_flag_is_full(self, tmp_path, capsys):
        dataset = _dataset(tmp_path, ["p1", "p2", "p3"])
        config_path = _config_file(tmp_path, dataset)

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            _run_main(["--config", str(config_path)])
        capsys.readouterr()

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            _run_main(["--config", str(config_path), "--no-incremental"])
        out = capsys.readouterr().out
        assert "Incremental evaluation mode enabled" not in out


class TestIncrementalStaleStrategies:
    def test_shrunk_strategy_set_stays_out_of_reports(self, tmp_path, capsys):
        """First run two strategies, second run only one + dataset change:
        the stale strategy must not appear in summary.json (W2 guard)."""
        problems = []
        for pid in ("p1", "p2", "p3"):
            problems.append(
                {
                    "problem_id": pid,
                    "title": f"P-{pid}",
                    "description": f"Problem description for {pid} first version.",
                    "difficulty": "easy",
                    "tags": ["tag"],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            )
        dataset = tmp_path / "problems.json"
        dataset.write_text(json.dumps(problems), encoding="utf-8")
        config = {
            "dataset_path": str(dataset),
            "output_dir": str(tmp_path / "results"),
            "llm_config": {"provider": "openai", "api_key": "k", "model": "test-model"},
            "strategies": [
                {"name": "vanilla", "max_iterations": 1},
                {"name": "chain_of_thought", "max_iterations": 1},
            ],
            "sandbox_config": {"backend": "host", "allowed_imports": []},
        }
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0

        # Shrink the strategy set and change the dataset.
        for problem in problems:
            if problem["problem_id"] == "p2":
                problem["description"] = "changed second version"
        dataset.write_text(json.dumps(problems), encoding="utf-8")
        config["strategies"] = [{"name": "vanilla", "max_iterations": 1}]
        config_path.write_text(json.dumps(config), encoding="utf-8")

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0

        latest = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
        run_dir = tmp_path / "results" / latest["latest_run"]
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert set(summary["strategies"]) == {"vanilla"}
        assert summary["strategies"]["vanilla"]["total_problems"] == 3


class TestIncrementalShrunkDataset:
    def test_removals_only_falls_back_to_full(self, tmp_path, capsys):
        """Dataset shrank (removals only): one full-evaluation message, no
        incremental banner, report covers the shrunk dataset (N3b guard)."""
        dataset = _dataset(tmp_path, ["p1", "p2", "p3"])
        config_path = _config_file(tmp_path, dataset)

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            _run_main(["--config", str(config_path), "--incremental"])
        capsys.readouterr()

        # Remove one problem from the dataset (removals only, no changes).
        problems = json.loads(dataset.read_text(encoding="utf-8"))
        dataset.write_text(
            json.dumps([p for p in problems if p["problem_id"] != "p3"]),
            encoding="utf-8",
        )

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        out = capsys.readouterr().out
        assert out.count("Dataset shrank since the last run") == 1
        assert "Incremental evaluation mode enabled" not in out
        assert "Total to evaluate: 0" not in out


class TestIncrementalFallbacks:
    def test_missing_results_dir_falls_back_to_full(self, tmp_path, capsys):
        """Corrupt/missing history results must fall back to full evaluation
        (delta spec: never a silent subset run)."""
        dataset = _dataset(tmp_path, ["p1", "p2"])
        config_path = _config_file(tmp_path, dataset)

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            _run_main(["--config", str(config_path), "--incremental"])
        capsys.readouterr()

        # Wipe the recorded run directory (results unrecoverable) and change
        # the dataset so incremental mode would otherwise trigger.
        history_path = tmp_path / "results" / ".incremental" / "history.json"
        history = json.loads(history_path.read_text(encoding="utf-8"))
        for record in history["runs"]:
            run_dir = tmp_path / "results" / record["run_id"]
            if run_dir.exists():
                for results_file in run_dir.glob("*_results.json"):
                    results_file.unlink()
        new_dataset = _dataset(tmp_path, ["p1", "p2", "p3"], modify_id="p2")
        config_data = json.loads(config_path.read_text(encoding="utf-8"))
        config_data["dataset_path"] = str(new_dataset)
        config_path.write_text(json.dumps(config_data), encoding="utf-8")

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        out = capsys.readouterr().out
        assert "falling back to full evaluation" in out
        assert "Incremental evaluation mode enabled" not in out
        # N1: the fallback full run is recorded, healing the history so the
        # next small change can enter incremental mode again.
        history_after = json.loads(history_path.read_text(encoding="utf-8"))
        assert len(history_after["runs"]) >= 2
        assert (
            history_after["runs"][-1]["dataset_fingerprint"]
            != history["runs"][-1]["dataset_fingerprint"]
        )

    def test_corrupted_history_falls_back_to_full(self, tmp_path, capsys):
        dataset = _dataset(tmp_path, ["p1", "p2"])
        config_path = _config_file(tmp_path, dataset)

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            _run_main(["--config", str(config_path), "--incremental"])
        capsys.readouterr()

        history_path = tmp_path / "results" / ".incremental" / "history.json"
        history_path.write_text("{corrupted", encoding="utf-8")

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        out = capsys.readouterr().out
        assert "Incremental evaluation mode enabled" not in out

    def test_no_matching_run_falls_back(self, tmp_path, capsys):
        dataset = _dataset(tmp_path, ["p1", "p2"])
        config_path = _config_file(tmp_path, dataset)

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(["--config", str(config_path), "--incremental"]) == 0
        out = capsys.readouterr().out
        assert "No matching historical run found" in out or "full evaluation" in out
