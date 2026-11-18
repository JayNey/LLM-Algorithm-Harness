"""
End-to-end tests for incremental evaluation (issue #87 follow-up fixes).

Proves the closed loop: first run evaluates everything and records history,
then a changed dataset triggers incremental mode that evaluates only the
changed problems, reuses historical results, and produces a merged report
with real (non-placeholder) metrics.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import LLMResponse, Problem, TokenUsage


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


def _read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def _latest_run(tmp_path):
    output = tmp_path / "results"
    return output / _read_json(output / "latest.json")["latest_run"]


def _result_sources(run, strategy="vanilla"):
    rows = _read_json(run / f"{strategy}_results.json")
    sources = {row["problem_id"]: row["source"] for row in rows}
    assert len(sources) == len(rows)
    return sources


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
    @pytest.mark.parametrize("legacy_success", [False, True])
    def test_zero_case_results_do_not_inflate_incremental_summary(self, tmp_path, legacy_success):
        dataset = _dataset(tmp_path, ["p1", "p2", "p3"])
        problems = json.loads(dataset.read_text(encoding="utf-8"))
        problems[2].pop("test_cases")
        problems[2].update(public_test_cases=[], needs_manual_completion=True)
        dataset.write_text(json.dumps(problems), encoding="utf-8")
        argv = ["--config", str(_config_file(tmp_path, dataset)), "--incremental"]
        output_dir = tmp_path / "results"

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0

        def latest_run():
            latest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
            return output_dir / latest["latest_run"]

        if legacy_success:
            prior = latest_run() / "vanilla_results.json"
            rows = json.loads(prior.read_text(encoding="utf-8"))
            skipped = next(row for row in rows if row["problem_id"] == "p3")
            skipped.update(status="success", evaluation_completed=True, error_message=None)
            prior.write_text(json.dumps(rows), encoding="utf-8")

        problems[0]["description"] = "Modified problem description."
        dataset.write_text(json.dumps(problems), encoding="utf-8")
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0

        run = latest_run()
        summary = json.loads((run / "summary.json").read_text(encoding="utf-8"))
        report = summary["strategies"]["vanilla"]
        assert report["total_problems"] == report["solved_problems"] == 2
        assert report["success_rate"] == 1.0
        rows = json.loads((run / "vanilla_results.json").read_text(encoding="utf-8"))
        skipped = next(row for row in rows if row["problem_id"] == "p3")
        assert skipped["status"] == "not_evaluable"
        assert skipped["source"] == ("fresh" if legacy_success else "reused")

    @pytest.mark.parametrize("report_name", ["vanilla", "cost_aware"])
    def test_second_run_evaluates_only_changed_and_merges(self, tmp_path, capsys, report_name):
        dataset = _dataset(tmp_path, ["p1", "p2", "p3"])
        config_path = _config_file(tmp_path, dataset)
        if report_name == "cost_aware":
            config = json.loads(config_path.read_text(encoding="utf-8"))
            config["difficulty_strategy"] = {"easy": "vanilla"}
            config_path.write_text(json.dumps(config), encoding="utf-8")

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
        # Latest run summary reflects the full merged dataset (4 problems).
        latest = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
        run_dir = tmp_path / "results" / latest["latest_run"]
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        report = summary["strategies"][report_name]
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


class TestIncrementalFingerprints:
    @pytest.mark.parametrize(
        "changed_setting", ["temperature", "system_prompt", "endpoint", "second_strategy"]
    )
    def test_config_changes_rerun_unchanged_problems(self, tmp_path, monkeypatch, changed_setting):
        dataset = _dataset(tmp_path, ["p1", "p2"])
        config_path = _config_file(tmp_path, dataset)
        config = _read_json(config_path)
        config["llm_config"].update(temperature=0.1, cache={"enabled": False})
        if changed_setting == "second_strategy":
            config["strategies"].append({"name": "chain_of_thought"})
        _write_json(config_path, config)
        argv = ["--config", str(config_path), "--incremental"]

        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0
            first = _latest_run(tmp_path)
            if changed_setting == "temperature":
                config["llm_config"]["temperature"] = 0.9
            elif changed_setting == "system_prompt":
                config["strategies"][0]["system_prompt"] = "Use the new generation prompt."
            elif changed_setting == "endpoint":
                monkeypatch.setenv("OPENAI_BASE_URL", "https://another.example/v1")
            else:
                config["strategies"][1]["temperature"] = 0.9
            _write_json(config_path, config)
            _dataset(tmp_path, ["p1", "p2", "p3"])
            assert _run_main(argv) == 0

        current = _latest_run(tmp_path)
        for strategy in config["strategies"]:
            assert _result_sources(current, strategy["name"]) == dict.fromkeys(
                ["p1", "p2", "p3"], "fresh"
            )
        runs = _read_json(tmp_path / "results" / ".incremental" / "history.json")["runs"]
        assert [row["run_id"] for row in runs] == [first.name, current.name]
        assert runs[0]["execution_fingerprint"] != runs[1]["execution_fingerprint"]

    def test_constraint_change_reruns_only_modified_and_added_problems(self, tmp_path):
        dataset = _dataset(tmp_path, ["p1", "p2"])
        argv = ["--config", str(_config_file(tmp_path, dataset)), "--incremental"]
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0
            first = _latest_run(tmp_path)
            _dataset(tmp_path, ["p1", "p2", "p3"])
            problems = _read_json(dataset)
            problems[0]["constraints"] = "The input must be a positive integer."
            _write_json(dataset, problems)
            assert _run_main(argv) == 0

        run = _latest_run(tmp_path)
        assert _result_sources(run) == {"p1": "fresh", "p2": "reused", "p3": "fresh"}
        metadata = _read_json(run / "metadata.json")
        assert metadata["incremental_mode"]["source_run_id"] == first.name
        assert metadata["incremental_mode"]["reused_results"] == 1
        assert (
            metadata["execution_fingerprint"]
            == _read_json(first / "metadata.json")["execution_fingerprint"]
        )
        assert _read_json(run / "summary.json")["strategies"]["vanilla"]["total_problems"] == 3

    @pytest.mark.parametrize(
        "field", ["execution_fingerprint", "fingerprint_version", "future_version"]
    )
    def test_old_history_is_kept_but_requires_a_full_run(self, tmp_path, field):
        dataset = _dataset(tmp_path, ["p1", "p2"])
        argv = ["--config", str(_config_file(tmp_path, dataset)), "--incremental"]
        history = tmp_path / "results" / ".incremental" / "history.json"
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0
            first = _latest_run(tmp_path)
            document = _read_json(history)
            record = document["runs"][0]
            if field == "future_version":
                record["fingerprint_version"] = 999
                record["newer_metadata"] = {"preserve": True}
            else:
                record.pop(field, None)
            _write_json(history, document)
            _dataset(tmp_path, ["p1", "p2", "p3"])
            assert _run_main(argv) == 0

        assert _result_sources(_latest_run(tmp_path)) == dict.fromkeys(["p1", "p2", "p3"], "fresh")
        assert _read_json(history)["runs"][0] == record
        assert record["run_id"] == first.name
        assert (first / "metadata.json").exists()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("title", "Another title"),
        ("description", "A different problem description."),
        ("difficulty", "hard"),
        ("tags", ["graphs"]),
        ("constraints", "The input must be positive."),
        ("unsupported_reason", "Unsupported judge"),
        ("input_output_mode", "stdin_stdout"),
        ("entry_point", "another(x)"),
        ("judge_config", {"comparison": "exact"}),
        ("public_test_cases", [{"input": {"x": 5}, "expected_output": 6}]),
        ("feedback_test_cases", [{"input": {"x": 2}, "expected_output": 3}]),
        ("hidden_test_cases", [{"input": {"x": 3}, "expected_output": 4}]),
    ],
)
def test_problem_fingerprint_tracks_evaluation_fields(tmp_path, field, value):
    from src.incremental.fingerprint import compute_problem_fingerprint

    payload = _read_json(_dataset(tmp_path, ["p1"]))[0]
    original = Problem.model_validate(payload)
    changed = Problem.model_validate({**original.model_dump(), field: value})
    assert compute_problem_fingerprint(changed) != compute_problem_fingerprint(original)


@pytest.mark.parametrize("run_dependent", ["budget", "examples"])
def test_run_dependent_execution_evaluates_the_full_selection(tmp_path, run_dependent):
    dataset = _dataset(tmp_path, ["p1", "p2"])
    config_path = _config_file(tmp_path, dataset)
    config = _read_json(config_path)
    strategy = "vanilla"
    if run_dependent == "budget":
        config.update(budget_cap_usd=10.0, budget_action="auto_stop")
        config["llm_config"]["model"] = "gpt-4o-mini"
    else:
        strategy = "few_shot_learning"
        config["strategies"][0]["name"] = strategy
    _write_json(config_path, config)
    argv = ["--config", str(config_path), "--incremental"]

    with patch("src.harness.LLMClient", side_effect=_llm_factory()):
        assert _run_main(argv) == 0
        _dataset(tmp_path, ["p1", "p2", "p3"])
        assert _run_main(argv) == 0
    assert _result_sources(_latest_run(tmp_path), strategy) == dict.fromkeys(
        ["p1", "p2", "p3"], "fresh"
    )


def test_few_shot_cannot_resume_an_incremental_reuse_plan(tmp_path):
    from src.main import select_incremental_results
    from src.models import HarnessConfig

    dataset = _dataset(tmp_path, ["p1"])
    config_path = _config_file(tmp_path, dataset)
    payload = _read_json(config_path)
    payload["strategies"][0]["name"] = "few_shot_learning"
    config = HarnessConfig.model_validate(payload)
    with pytest.raises(ValueError, match="cannot resume incremental reuse"):
        select_incremental_results(config, [], "old-fingerprint", {}, source_run_id="old-run")


@pytest.mark.parametrize("missing_source", [False, True])
def test_resume_uses_the_original_incremental_selection(tmp_path, missing_source, capsys):
    from src.task_service import TaskService

    dataset = _dataset(tmp_path, ["p1", "p2"])
    config_path = _config_file(tmp_path, dataset)
    config = _read_json(config_path)
    config["llm_config"]["cache"] = {"enabled": False}
    config["max_workers"] = 1
    _write_json(config_path, config)
    argv = ["--config", str(config_path), "--incremental"]
    run_id = "interrupted-incremental"
    run = TaskService.run

    def pause_after_one(self, selected_run_id, worker, **kwargs):
        if selected_run_id == run_id:
            kwargs["pause_when"] = lambda record: record.completed_units >= 1
        return run(self, selected_run_id, worker, **kwargs)

    generate = MagicMock()
    create_client = _llm_factory()

    def tracked_client(settings):
        client = create_client(settings)
        generate.return_value = client.generate.return_value
        client.generate = generate
        return client

    with patch("src.harness.LLMClient", side_effect=tracked_client):
        assert _run_main(argv) == 0
        original_source = _latest_run(tmp_path)
        _dataset(tmp_path, ["p1", "p2", "p3", "p4"])
        with patch.object(TaskService, "run", pause_after_one):
            assert _run_main([*argv, "--run-id", run_id]) == 0
        paused_run = _latest_run(tmp_path)
        checkpoint = _read_json(tmp_path / "results" / "tasks" / f"{run_id}.json")
        assert checkpoint["state"] == "paused"
        assert [unit["problem_id"] for unit in checkpoint["units"]] == ["p3", "p4"]

        # A later compatible run must never replace the source of the interrupted run.
        assert _run_main(argv) == 0
        if missing_source:
            (original_source / "vanilla_results.json").unlink()
        generate.reset_mock()
        resume_argv = [*argv, "--resume", "--run-id", run_id]
        if missing_source:
            assert _run_main(resume_argv) == 1
            assert "Historical results are missing or incomplete" in capsys.readouterr().err
            assert generate.call_count == 0
            return

        assert _run_main(resume_argv) == 0
        assert generate.call_count == 1
        assert _run_main(resume_argv) == 0
        assert generate.call_count == 1

    assert _latest_run(tmp_path) == paused_run
    assert _result_sources(paused_run) == {
        "p1": "reused",
        "p2": "reused",
        "p3": "fresh",
        "p4": "fresh",
    }
    assert _read_json(paused_run / "summary.json")["strategies"]["vanilla"]["total_problems"] == 4
    metadata = _read_json(paused_run / "metadata.json")
    assert metadata["incremental_mode"]["source_run_id"] == original_source.name
    history = _read_json(tmp_path / "results" / ".incremental" / "history.json")
    assert sum(record["run_id"] == run_id for record in history["runs"]) == 1


class TestIncrementalStaleStrategies:
    def test_shrunk_strategy_set_stays_out_of_reports(self, tmp_path, capsys):
        """Removing a strategy invalidates the old run's execution configuration."""
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

        assert "Incremental evaluation mode enabled" not in capsys.readouterr().out
        latest = json.loads((tmp_path / "results" / "latest.json").read_text(encoding="utf-8"))
        run_dir = tmp_path / "results" / latest["latest_run"]
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        assert set(summary["strategies"]) == {"vanilla"}
        assert summary["strategies"]["vanilla"]["total_problems"] == 3
        assert _result_sources(run_dir) == dict.fromkeys(["p1", "p2", "p3"], "fresh")


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
    @pytest.mark.parametrize(
        "history_gap", ["added_strategy", "missing_file", "missing_record", "duplicate", "bad_json"]
    )
    def test_unusable_history_falls_back_to_complete_run(self, tmp_path, capsys, history_gap):
        problem_ids = ["p1", "p2", "p3"]
        dataset = _dataset(tmp_path, problem_ids)
        config_path = _config_file(tmp_path, dataset)
        config = json.loads(config_path.read_text(encoding="utf-8"))
        second_strategy = {"name": "chain_of_thought", "max_iterations": 1}
        if history_gap == "missing_file":
            config["strategies"].append(second_strategy)
            config_path.write_text(json.dumps(config), encoding="utf-8")

        argv = ["--config", str(config_path), "--incremental"]
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0
        capsys.readouterr()

        output_dir = tmp_path / "results"
        history_path = output_dir / ".incremental" / "history.json"
        first_run = json.loads(history_path.read_text(encoding="utf-8"))["runs"][-1]
        first_result_dir = Path(first_run["result_path"])
        vanilla_file = first_result_dir / "vanilla_results.json"
        if history_gap == "added_strategy":
            config["strategies"].append(second_strategy)
            config_path.write_text(json.dumps(config), encoding="utf-8")
        elif history_gap == "missing_file":
            (first_result_dir / "chain_of_thought_results.json").unlink()
        elif history_gap == "bad_json":
            vanilla_file.write_text("{invalid", encoding="utf-8")
        else:
            rows = json.loads(vanilla_file.read_text(encoding="utf-8"))
            if history_gap == "missing_record":
                rows = [row for row in rows if row["problem_id"] != "p3"]
            else:
                rows.append(next(row for row in rows if row["problem_id"] == "p3"))
            vanilla_file.write_text(json.dumps(rows), encoding="utf-8")

        _dataset(tmp_path, problem_ids, modify_id="p1")
        with patch("src.harness.LLMClient", side_effect=_llm_factory()):
            assert _run_main(argv) == 0
        out = capsys.readouterr().out

        latest = json.loads((output_dir / "latest.json").read_text(encoding="utf-8"))
        run_dir = output_dir / latest["latest_run"]
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        strategies = {strategy["name"] for strategy in config["strategies"]}
        assert set(summary["strategies"]) == strategies
        for strategy in strategies:
            report = summary["strategies"][strategy]
            assert report["total_problems"] == len(problem_ids), strategy
            assert report["success_rate"] == 1.0
            rows = json.loads((run_dir / f"{strategy}_results.json").read_text(encoding="utf-8"))
            assert sorted(row["problem_id"] for row in rows) == problem_ids

        metadata = json.loads((run_dir / "metadata.json").read_text(encoding="utf-8"))
        assert metadata["incremental_mode"]["enabled"] is False

        runs = json.loads(history_path.read_text(encoding="utf-8"))["runs"]
        assert len(runs) == 2
        assert runs[-1]["run_id"] == latest["latest_run"]
        assert Path(runs[-1]["result_path"]) == run_dir
        assert set(runs[-1]["dataset_fingerprint"]) == set(problem_ids)
        assert runs[-1]["problem_count"] == len(problem_ids)
        assert "Incremental evaluation mode enabled" not in out
        assert "falling back to full evaluation" in out

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
