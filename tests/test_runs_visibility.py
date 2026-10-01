"""
Tests for run-state visibility: runs list/clean and the startup resume hint
(issue #88).
"""

import argparse
from unittest.mock import patch

import pytest

from src.main import run_runs_command
from src.models import ExecutionResult, HarnessConfig, LLMConfig, StrategyConfig
from src.runs import find_matching_unfinished, summarize_run
from src.task_service import TaskRecord, TaskService, TaskUnit


def make_record(run_id, state, completed, total, results=None, fingerprint="cfg-1"):
    units = []
    for index in range(total):
        result = None
        if index < completed:
            payload = (results or [None] * total)[index]
            result = payload.model_dump(mode="json") if payload is not None else None
        units.append(
            TaskUnit(
                unit_id=f"vanilla:p{index}:0",
                strategy="vanilla",
                problem_id=f"p{index}",
                status="completed" if result is not None else "queued",
                result=result,
            )
        )
    return TaskRecord(
        run_id=run_id,
        state=state,
        total_units=total,
        completed_units=completed,
        config_fingerprint=fingerprint,
        dataset_fingerprint="data-1",
        units=units,
    )


def priced_result(cost):
    return ExecutionResult(
        problem_id="p",
        strategy="vanilla",
        generated_code="",
        status="success",
        llm_traces=[
            {
                "prompt_tokens": 1,
                "completion_tokens": 1,
                "total_tokens": 2,
                "pricing_metadata": {"total_cost": cost, "usage_known": True},
            }
        ],
    )


class TestSummarizeRun:
    def test_progress_cost_and_resumable(self):
        record = make_record(
            "run-a",
            "paused",
            completed=2,
            total=3,
            results=[priced_result(0.5), priced_result(0.25)],
        )
        summary = summarize_run(record)
        assert summary["run_id"] == "run-a"
        assert summary["completed"] == 2
        assert summary["total"] == 3
        assert summary["resumable"] is True
        assert summary["cost_usd"] == 0.75
        assert summary["unknown_usage_results"] == 0

    def test_completed_run_is_not_resumable(self):
        record = make_record("run-b", "completed", completed=1, total=1)
        assert summarize_run(record)["resumable"] is False

    def test_unknown_usage_counted_not_accumulated(self):
        unknown = ExecutionResult(
            problem_id="p",
            strategy="vanilla",
            generated_code="",
            status="success",
            llm_traces=[{"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6}],
        )
        record = make_record(
            "run-c",
            "running",
            completed=2,
            total=2,
            results=[priced_result(0.5), unknown],
        )
        summary = summarize_run(record)
        assert summary["cost_usd"] == 0.5
        assert summary["unknown_usage_results"] == 1


class TestFindMatchingUnfinished:
    def _service_with(self, tmp_path, records):
        service = TaskService(tmp_path / "tasks")
        for record in records:
            service.store.save(record)
        return service

    def test_matches_fingerprint_and_unfinished_only(self, tmp_path):
        service = self._service_with(
            tmp_path,
            [
                make_record("match-paused", "paused", 1, 2, fingerprint="cfg-1"),
                make_record("other-config", "paused", 1, 2, fingerprint="cfg-2"),
                make_record("match-done", "completed", 2, 2, fingerprint="cfg-1"),
            ],
        )
        matches = find_matching_unfinished(service, "cfg-1", "data-1")
        assert [record.run_id for record in matches] == ["match-paused"]


class TestRunsCommand:
    def _prepare(self, tmp_path):
        service = TaskService(tmp_path / "results" / "tasks")
        service.store.save(make_record("done-run", "completed", 2, 2))
        service.store.save(
            make_record(
                "paused-run",
                "paused",
                1,
                2,
                results=[priced_result(0.4)],
            )
        )
        return service

    def test_list_defaults_to_resumable(self, tmp_path, capsys):
        self._prepare(tmp_path)
        args = argparse.Namespace(
            runs_command="list", all=False, output=str(tmp_path / "results"), log_format="console"
        )
        assert run_runs_command(args) == 0
        out = capsys.readouterr().out
        assert "paused-run" in out
        assert "done-run" not in out
        assert "0.4000" in out

    def test_list_all_includes_completed(self, tmp_path, capsys):
        self._prepare(tmp_path)
        args = argparse.Namespace(
            runs_command="list", all=True, output=str(tmp_path / "results"), log_format="console"
        )
        assert run_runs_command(args) == 0
        out = capsys.readouterr().out
        assert "paused-run" in out and "done-run" in out

    def test_clean_force_removes_only_completed(self, tmp_path, capsys):
        service = self._prepare(tmp_path)
        args = argparse.Namespace(
            runs_command="clean",
            force=True,
            output=str(tmp_path / "results"),
            log_format="console",
        )
        assert run_runs_command(args) == 0
        out = capsys.readouterr().out
        assert "Deleted: done-run" in out
        assert service.get("paused-run").state == "paused"
        with pytest.raises(FileNotFoundError):
            service.get("done-run")

    def test_clean_without_confirm_skips_on_n(self, tmp_path, monkeypatch, capsys):
        self._prepare(tmp_path)
        monkeypatch.setattr("builtins.input", lambda prompt="": "n")
        args = argparse.Namespace(
            runs_command="clean",
            force=False,
            output=str(tmp_path / "results"),
            log_format="console",
        )
        assert run_runs_command(args) == 0
        out = capsys.readouterr().out
        assert "Skipped: done-run" in out
        service = TaskService(tmp_path / "results" / "tasks")
        assert service.get("done-run").state == "completed"

    def test_missing_output_dir_is_clean(self, tmp_path, capsys):
        args = argparse.Namespace(
            runs_command="list",
            all=False,
            output=str(tmp_path / "nonexistent"),
            log_format="console",
        )
        assert run_runs_command(args) == 0
        assert "No persisted runs" in capsys.readouterr().out


class TestResumeHint:
    def _config(self, output_dir):
        from src.models import HarnessConfig, LLMConfig, StrategyConfig

        return HarnessConfig(
            dataset_path="data/problems.json",
            llm_config=LLMConfig(provider="openai", api_key="k", model="m"),
            strategies=[StrategyConfig(name="vanilla")],
            output_dir=output_dir,
        )

    def test_hint_prints_matching_unfinished_run(self, tmp_path, capsys):
        from src.main import maybe_print_resume_hint

        service = TaskService(tmp_path / "tasks")
        record = make_record("match-me", "paused", 1, 2, fingerprint="cfg-x")
        record.config_fingerprint = "cfg-x"
        service.store.save(record)
        config = self._config(str(tmp_path))
        from src.task_service import TaskService as svc

        monkey_fingerprint = {"cfg": "cfg-x", "data": "data-1"}
        record.config_fingerprint = svc.config_fingerprint(config)
        service.store.save(record)

        with patch.object(
            svc,
            "dataset_fingerprint",
            staticmethod(lambda path: "data-1"),
        ):
            maybe_print_resume_hint(config)
        out = capsys.readouterr().out
        assert "match-me" in out
        assert "--resume --run-id match-me" in out
        assert "no other process" in out

    def test_hint_silent_without_store(self, tmp_path, capsys):
        from src.main import maybe_print_resume_hint

        maybe_print_resume_hint(self._config(str(tmp_path)))
        assert capsys.readouterr().out == ""

    def test_summarize_skips_unreadable_unit_results(self, tmp_path):
        record = make_record("run-x", "running", 2, 2)
        record.units[0].result = {"foo": "bar"}
        record.units[1].result = priced_result(0.5).model_dump(mode="json")
        summary = summarize_run(record)
        assert summary["cost_usd"] == 0.5
        assert summary["unknown_usage_results"] == 0

    def test_output_flag_reachable_via_real_cli(self, tmp_path):
        """Regression: runs list/clean must accept --output (IMPORTANT-1)."""
        import subprocess
        import sys

        result = subprocess.run(
            [sys.executable, "-m", "src.main", "runs", "list", "--output", str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stderr
        assert "No persisted runs" in result.stdout


class TestStartupHintMatching:
    def test_fingerprint_includes_budget_and_dataset(self, tmp_path):
        """The hint matcher is fingerprint-driven: config/dataset changes break it."""
        base = HarnessConfig(
            dataset_path="data/problems.json",
            llm_config=LLMConfig(provider="openai", api_key="k", model="m"),
            strategies=[StrategyConfig(name="vanilla")],
        )
        from src.task_service import TaskService as svc

        fp1 = svc.config_fingerprint(base)
        changed = base.model_copy(update={"budget_cap_usd": 1.0})
        assert fp1 != svc.config_fingerprint(changed)
