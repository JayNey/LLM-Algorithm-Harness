"""Regression tests for benchmark run-level budgets (review P0-4).

The benchmark form exposes ``budget_cap_usd``, but the executor runs the
harness through its non task-service path. That path must honor an
auto-stop cap at unit boundaries instead of failing the whole run.
"""

import json
from unittest.mock import Mock

from src.harness import AlgorithmHarness
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
)


def _problem(problem_id):
    return {
        "problem_id": problem_id,
        "title": f"P-{problem_id}",
        "description": "A problem description long enough",
        "difficulty": "easy",
        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
    }


def _dataset(tmp_path, problem_ids=("p1", "p2", "p3")):
    path = tmp_path / "problems.json"
    path.write_text(json.dumps([_problem(pid) for pid in problem_ids]), encoding="utf-8")
    return path


def _priced_result(problem_id, cost, strategy="vanilla"):
    return ExecutionResult(
        problem_id=problem_id,
        strategy=strategy,
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


def _patch_runtimes(monkeypatch, cost):
    calls = []

    def fake_prepare(self, strategy_config):
        strategy = Mock()

        def execute(problem):
            calls.append((strategy_config.name, problem.problem_id))
            return _priced_result(problem.problem_id, cost, strategy_config.name)

        strategy.execute.side_effect = execute
        return strategy, Mock()

    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", fake_prepare)
    return calls


def _harness(tmp_path, budget_cap_usd, budget_action):
    return AlgorithmHarness(
        HarnessConfig(
            dataset_path=str(_dataset(tmp_path)),
            output_dir=str(tmp_path / "results"),
            llm_config=LLMConfig(provider="openai", api_key="key", model="test-model"),
            sandbox_config=SandboxConfig(backend="host"),
            strategies=[StrategyConfig(name="vanilla")],
            budget_cap_usd=budget_cap_usd,
            budget_action=budget_action,
        )
    )


def test_non_task_harness_pauses_at_budget_cap_instead_of_failing(tmp_path, monkeypatch):
    calls = _patch_runtimes(monkeypatch, cost=0.6)
    harness = _harness(tmp_path, budget_cap_usd=1.0, budget_action="auto_stop")

    reports = harness.run()

    # First unit reaches the cap; the second is never dispatched.
    assert calls == [("vanilla", "p1"), ("vanilla", "p2")]
    assert harness.paused is True
    assert reports["vanilla"].solved_problems == 2


def test_budget_not_reached_runs_every_unit(tmp_path, monkeypatch):
    calls = _patch_runtimes(monkeypatch, cost=0.6)
    harness = _harness(tmp_path, budget_cap_usd=10.0, budget_action="auto_stop")

    reports = harness.run()

    assert calls == [("vanilla", "p1"), ("vanilla", "p2"), ("vanilla", "p3")]
    assert harness.paused is False
    assert reports["vanilla"].solved_problems == 3


def test_budget_reached_on_last_unit_completes_instead_of_pausing(tmp_path, monkeypatch):
    calls = _patch_runtimes(monkeypatch, cost=0.5)
    harness = _harness(tmp_path, budget_cap_usd=1.5, budget_action="auto_stop")

    reports = harness.run()

    # Exactly at the cap, but no unit remains to dispatch: the run completes
    # instead of parking in a paused state it can never leave.
    assert calls == [("vanilla", "p1"), ("vanilla", "p2"), ("vanilla", "p3")]
    assert harness.paused is False
    assert reports["vanilla"].solved_problems == 3


def test_benchmark_executor_reports_budget_pause(tmp_path, monkeypatch):
    from src.benchmark.executor import BenchmarkExecutor
    from src.benchmark.suite import BenchmarkSuite

    calls = _patch_runtimes(monkeypatch, cost=0.6)
    config = HarnessConfig(
        dataset_path=str(_dataset(tmp_path)),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="key", model="test-model"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[StrategyConfig(name="vanilla")],
        budget_cap_usd=1.0,
        budget_action="auto_stop",
    )
    executor = BenchmarkExecutor(
        BenchmarkSuite(name="budget-suite", problems=["p1", "p2", "p3"]), config
    )

    results = executor.execute()

    assert calls == [("vanilla", "p1"), ("vanilla", "p2")]
    assert executor.paused is True
    assert results["problems_evaluated"] == 3
    assert results["strategies"]["vanilla"]["passed"] == 2


def test_resumed_replay_counts_toward_budget_without_rerunning(tmp_path, monkeypatch):
    calls = _patch_runtimes(monkeypatch, cost=0.6)
    checkpoint_dir = tmp_path / "units"

    first = _harness(tmp_path, budget_cap_usd=1.0, budget_action="auto_stop")
    first.checkpoint_dir = checkpoint_dir
    first.run()
    assert calls == [("vanilla", "p1"), ("vanilla", "p2")]
    assert first.paused is True

    resumed = _harness(tmp_path, budget_cap_usd=1.0, budget_action="auto_stop")
    resumed.checkpoint_dir = checkpoint_dir
    resumed.run()

    # Replayed units are settled but never re-executed; the unchanged cap
    # pauses again instead of spending past it.
    assert calls == [("vanilla", "p1"), ("vanilla", "p2")]
    assert resumed.paused is True
