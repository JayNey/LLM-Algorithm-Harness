"""Tests for the benchmark evaluation executor."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.benchmark.executor import BenchmarkExecutor
from src.benchmark.suite import load_benchmark_suite
from src.models import (
    HarnessConfig,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
    StrategyReport,
)


def _report(strategy, total, solved):
    return StrategyReport(
        strategy_name=strategy,
        total_problems=total,
        solved_problems=solved,
        failed_problems=total - solved,
        success_rate=solved / total if total else 0.0,
        avg_attempts_per_problem=1.0,
        total_tokens=100 * total,
        avg_tokens_per_problem=100.0,
        estimated_cost_usd=0.01 * total,
    )


def _setup(tmp_path, suite_problem_ids=("bm-1", "bm-2"), dataset_ids=("bm-1", "bm-2", "other")):
    problems = [
        {
            "problem_id": problem_id,
            "title": f"P-{problem_id}",
            "description": "A problem description long enough",
            "difficulty": "easy",
            "tags": ["tag"],
            "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
        }
        for problem_id in dataset_ids
    ]
    dataset = tmp_path / "problems.json"
    dataset.write_text(json.dumps(problems), encoding="utf-8")

    suite_payload = {
        "name": "bm-suite",
        "problems": list(suite_problem_ids),
        "version": "1.0",
    }
    suite_path = tmp_path / "benchmark.json"
    suite_path.write_text(json.dumps(suite_payload), encoding="utf-8")

    suite = load_benchmark_suite(suite_path)
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="key", model="test-model"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[StrategyConfig(name="vanilla")],
    )
    return BenchmarkExecutor(suite, config)


class TestBenchmarkExecutor:
    def test_execute_runs_harness_and_collects_results(self, tmp_path):
        executor = _setup(tmp_path)
        reports = {"vanilla": _report("vanilla", total=2, solved=1)}

        with (
            patch.object(executor, "config", executor.config),
            patch("src.benchmark.executor.AlgorithmHarness") as harness_cls,
        ):
            harness_cls.return_value.run.return_value = reports
            results = executor.execute()

        assert results["suite"]["name"] == "bm-suite"
        assert results["problems_evaluated"] == 2
        assert results["problems_missing"] == 0
        strategy = results["strategies"]["vanilla"]
        assert strategy == {
            "total": 2,
            "passed": 1,
            "failed": 1,
            "accuracy": 0.5,
            "avg_attempts": 1.0,
            "total_tokens": 200,
            "total_cost": 0.02,
        }
        # Config restored after execution
        assert "other" in Path(executor.config.dataset_path).read_text(encoding="utf-8")
        assert executor.config.problem_filters is None
        # Temp dataset cleaned up
        leftovers = list(tmp_path.glob("tmp*.json"))
        assert leftovers == []

    def test_execute_restores_original_filters_when_harness_fails(self, tmp_path):
        executor = _setup(tmp_path)
        executor.config.problem_filters = {"difficulty": "easy"}
        original = executor.config.problem_filters

        with patch("src.benchmark.executor.AlgorithmHarness") as harness_cls:
            harness_cls.return_value.run.side_effect = RuntimeError("boom")
            with pytest.raises(RuntimeError):
                executor.execute()

        assert executor.config.problem_filters == original

    def test_all_suite_problems_missing_raises(self, tmp_path):
        executor = _setup(tmp_path, suite_problem_ids=("ghost-1",))
        with pytest.raises(ValueError, match="No problems found in benchmark suite"):
            executor.execute()

    def test_partial_missing_problems_still_executes(self, tmp_path):
        executor = _setup(tmp_path, suite_problem_ids=("bm-1", "ghost-9"))
        reports = {"vanilla": _report("vanilla", total=1, solved=1)}

        with patch("src.benchmark.executor.AlgorithmHarness") as harness_cls:
            harness_cls.return_value.run.return_value = reports
            results = executor.execute()

        assert results["problems_evaluated"] == 1
        assert results["problems_missing"] == 1
