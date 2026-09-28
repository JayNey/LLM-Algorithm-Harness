"""
Tests for cost-aware strategy selection and run-level budget downgrade (#56b).
"""

import argparse
import threading
from unittest.mock import Mock

import pytest

from src.cost_strategy import (
    CostAwareSelector,
    RunCostMonitor,
)
from src.harness import AlgorithmHarness
from src.main import SUPPORTED_STRATEGIES, apply_cli_overrides
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
)


def make_selector(mapping):
    return CostAwareSelector(mapping, allowed_strategies=list(SUPPORTED_STRATEGIES))


class TestCostAwareSelector:
    def test_select_routes_by_difficulty(self):
        selector = make_selector(
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            }
        )
        assert selector.select("easy") == "vanilla"
        assert selector.select("medium") == "chain_of_thought"
        assert selector.select("hard") == "multi_round_feedback"

    def test_rejects_unknown_difficulty(self):
        with pytest.raises(ValueError, match="Unknown difficulty"):
            make_selector({"extreme": "vanilla"})

    def test_rejects_unknown_strategy(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            make_selector({"easy": "no_such_strategy"})

    def test_rejects_empty_mapping(self):
        with pytest.raises(ValueError, match="must not be empty"):
            make_selector({})

    def test_select_uncovered_difficulty_fails(self):
        selector = make_selector({"easy": "vanilla"})
        with pytest.raises(ValueError, match="not covered"):
            selector.select("hard")

    def test_validate_coverage(self):
        selector = make_selector({"easy": "vanilla", "medium": "vanilla"})
        selector.validate_coverage(["easy", "medium"])
        # Missing and unknown difficulty labels (including None) are uncovered.
        with pytest.raises(ValueError, match="not covered by the"):
            selector.validate_coverage(["easy", "hard"])
        with pytest.raises(ValueError, match="not covered by the"):
            selector.validate_coverage(["easy", None])

    def test_cheapest_strategy_follows_ladder(self):
        full = make_selector(
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            }
        )
        assert full.cheapest_strategy == "vanilla"

        partial = make_selector({"medium": "chain_of_thought", "hard": "multi_round_feedback"})
        assert partial.cheapest_strategy == "chain_of_thought"

    def test_cheapest_strategy_falls_back_outside_ladder(self):
        selector = CostAwareSelector(
            {"easy": "custom_a", "hard": "custom_b"},
            allowed_strategies=["custom_a", "custom_b"],
        )
        assert selector.cheapest_strategy == "custom_a"


def make_result(shape="known", cost=0.5):
    """Build an ExecutionResult with a controlled trace pricing shape.

    Shapes: known (priced, usage known), cost_none (pricing present but
    total_cost None), usage_unknown (usage_known False), no_pricing (tokens
    without pricing metadata), empty (no traces at all).
    """
    if shape == "empty":
        traces = []
    elif shape == "no_pricing":
        traces = [{"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}]
    elif shape == "cost_none":
        traces = [{"pricing_metadata": {"total_cost": None, "usage_known": True}}]
    elif shape == "usage_unknown":
        traces = [{"pricing_metadata": {"total_cost": cost, "usage_known": False}}]
    else:
        traces = [{"pricing_metadata": {"total_cost": cost, "usage_known": True}}]
    return ExecutionResult(
        problem_id="p",
        strategy="vanilla",
        generated_code="",
        status="success",
        llm_traces=traces,
    )


class TestRunCostMonitor:
    def test_accumulates_known_cost(self):
        monitor = RunCostMonitor(budget_cap_usd=1.0)
        monitor.add_result(make_result(cost=0.6))
        monitor.add_result(make_result(cost=0.3))
        assert monitor.snapshot()["accumulated_cost_usd"] == pytest.approx(0.9)
        assert not monitor.over_cap
        monitor.add_result(make_result(cost=0.2))
        assert monitor.over_cap

    def test_unknown_usage_counted_not_accumulated(self):
        monitor = RunCostMonitor(budget_cap_usd=0.5)
        monitor.add_result(make_result("no_pricing"))
        monitor.add_result(make_result("usage_unknown", cost=0.2))
        monitor.add_result(make_result("cost_none"))
        snapshot = monitor.snapshot()
        assert snapshot["accumulated_cost_usd"] == 0.0
        assert snapshot["unknown_usage_results"] == 3
        assert not monitor.over_cap

    def test_call_free_result_is_not_flagged_unknown(self):
        monitor = RunCostMonitor(budget_cap_usd=0.5)
        free = ExecutionResult(
            problem_id="p",
            strategy="vanilla",
            generated_code="",
            status="budget_exhausted",
        )
        monitor.add_result(free)
        snapshot = monitor.snapshot()
        assert snapshot["unknown_usage_results"] == 0
        assert not monitor.over_cap

    def test_no_cap_never_triggers(self):
        monitor = RunCostMonitor()
        monitor.add_result(make_result(cost=100.0))
        assert not monitor.over_cap
        assert monitor.snapshot()["budget_cap_usd"] is None

    def test_reaching_cap_exactly_triggers(self):
        monitor = RunCostMonitor(budget_cap_usd=0.5)
        monitor.add_result(make_result(cost=0.5))
        assert monitor.over_cap

    def test_record_downgrade_first_trigger(self):
        monitor = RunCostMonitor(budget_cap_usd=1.0)
        assert monitor.record_downgrade() is True
        assert monitor.record_downgrade() is False
        assert monitor.snapshot()["downgraded_problems"] == 2

    def test_concurrent_add_results(self):
        monitor = RunCostMonitor(budget_cap_usd=1000.0)

        def worker():
            for _ in range(50):
                monitor.add_result(make_result(cost=0.1))

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert monitor.snapshot()["accumulated_cost_usd"] == pytest.approx(40.0)


class TestModelFields:
    def test_cost_downgraded_defaults_false(self):
        result = ExecutionResult(
            problem_id="p", strategy="vanilla", generated_code="", status="success"
        )
        assert result.cost_downgraded is False

    def test_legacy_result_json_without_new_field(self):
        legacy = {
            "problem_id": "p",
            "strategy": "vanilla",
            "generated_code": "",
            "status": "success",
        }
        assert ExecutionResult.model_validate(legacy).cost_downgraded is False

    def test_budget_cap_must_be_positive(self):
        base = dict(
            dataset_path="data/problems.json",
            llm_config=LLMConfig(provider="openai", api_key="k", model="m"),
            strategies=[StrategyConfig(name="vanilla")],
        )
        with pytest.raises(Exception):
            HarnessConfig(**base, budget_cap_usd=0)
        config = HarnessConfig(**base, budget_cap_usd=2.5)
        assert config.budget_cap_usd == 2.5
        assert config.difficulty_strategy is None


class TestCliOverrides:
    @staticmethod
    def make_args(**kwargs):
        defaults = dict(
            dataset=None,
            output=None,
            strategy=None,
            difficulty=None,
            tags=None,
            limit=None,
            difficulty_strategy=None,
            budget_cap=None,
        )
        defaults.update(kwargs)
        return argparse.Namespace(**defaults)

    @staticmethod
    def make_config():
        return HarnessConfig(
            dataset_path="data/problems.json",
            llm_config=LLMConfig(provider="openai", api_key="k", model="m"),
            strategies=[
                StrategyConfig(name="vanilla"),
                StrategyConfig(name="chain_of_thought"),
                StrategyConfig(name="multi_round_feedback"),
            ],
        )

    def test_parses_mapping_and_cap(self):
        config = apply_cli_overrides(
            self.make_config(),
            self.make_args(
                difficulty_strategy=[
                    "easy=vanilla",
                    "medium=chain_of_thought",
                    "hard=multi_round_feedback",
                ],
                budget_cap=5.0,
            ),
        )
        assert config.difficulty_strategy == {
            "easy": "vanilla",
            "medium": "chain_of_thought",
            "hard": "multi_round_feedback",
        }
        assert config.budget_cap_usd == 5.0

    def test_rejects_malformed_pair(self):
        with pytest.raises(ValueError, match="DIFF=STRATEGY"):
            apply_cli_overrides(self.make_config(), self.make_args(difficulty_strategy=["easy"]))

    def test_rejects_duplicate_difficulty(self):
        with pytest.raises(ValueError, match="Duplicate"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(difficulty_strategy=["easy=vanilla", "easy=vanilla"]),
            )

    def test_budget_cap_requires_mapping(self):
        with pytest.raises(ValueError, match="requires --difficulty-strategy"):
            apply_cli_overrides(self.make_config(), self.make_args(budget_cap=5.0))

    def test_selector_conflicts_with_strategy_flag(self):
        with pytest.raises(ValueError, match="cannot be combined"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(
                    difficulty_strategy=["easy=vanilla"],
                    strategy="vanilla",
                ),
            )

    def test_rejects_unknown_strategy_name(self):
        with pytest.raises(ValueError, match="Unknown strategy"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(difficulty_strategy=["easy=nope"]),
            )


def write_dataset(path, problems):
    import json

    path.write_text(json.dumps(problems))


def problem_payload(problem_id, difficulty):
    return {
        "problem_id": problem_id,
        "title": f"P-{problem_id}",
        "description": "A problem description long enough",
        "difficulty": difficulty,
        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
    }


def patch_runtimes(monkeypatch, costs):
    """Patch strategy runtimes; each mock records (strategy, problem_id) calls."""
    calls = []

    def fake_prepare(self, strategy_config):
        cost = costs[strategy_config.name]
        strategy = Mock()

        def execute(problem):
            calls.append((strategy_config.name, problem.problem_id))
            return ExecutionResult(
                problem_id=problem.problem_id,
                strategy=strategy_config.name,
                generated_code="",
                status="success",
                llm_traces=[
                    {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                        "pricing_metadata": {
                            "total_cost": cost,
                            "usage_known": True,
                        },
                    }
                ],
            )

        strategy.execute.side_effect = execute
        return strategy, Mock()

    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", fake_prepare)
    return calls


def make_harness(tmp_path, problems, difficulty_strategy, budget_cap_usd=None):
    dataset = tmp_path / "problems.json"
    write_dataset(dataset, problems)
    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="key", model="test-model"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=[
            StrategyConfig(name="vanilla"),
            StrategyConfig(name="chain_of_thought"),
            StrategyConfig(name="multi_round_feedback"),
        ],
        difficulty_strategy=difficulty_strategy,
        budget_cap_usd=budget_cap_usd,
        max_workers=1,
    )
    return AlgorithmHarness(config)


class TestHarnessCostAwareIntegration:
    def test_problems_route_by_difficulty(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.0, "chain_of_thought": 0.0, "multi_round_feedback": 0.0},
        )
        harness = make_harness(
            tmp_path,
            [
                problem_payload("p-easy", "easy"),
                problem_payload("p-hard", "hard"),
            ],
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
        )
        reports = harness.run(use_task_service=True, run_id="run-route")

        assert calls == [("vanilla", "p-easy"), ("multi_round_feedback", "p-hard")]
        assert set(reports) == {"cost_aware"}
        assert reports["cost_aware"].total_problems == 2
        assert [r.strategy for r in harness.results["cost_aware"]] == [
            "vanilla",
            "multi_round_feedback",
        ]
        assert all(not r.cost_downgraded for r in harness.results["cost_aware"])
        assert harness.cost_monitor is not None
        assert harness.cost_monitor.snapshot()["accumulated_cost_usd"] == 0.0

    def test_budget_cap_downgrades_remaining_problems(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        harness = make_harness(
            tmp_path,
            [
                problem_payload("p1", "easy"),
                problem_payload("p2", "medium"),
                problem_payload("p3", "hard"),
            ],
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
            budget_cap_usd=1.0,
        )
        harness.run(use_task_service=True, run_id="run-cap")

        # p1: vanilla (0.6 accumulated, under cap); p2: chain_of_thought
        # (1.2 accumulated, cap reached); p3: downgraded to cheapest (vanilla).
        assert calls == [
            ("vanilla", "p1"),
            ("chain_of_thought", "p2"),
            ("vanilla", "p3"),
        ]
        results = harness.results["cost_aware"]
        assert [r.cost_downgraded for r in results] == [False, False, True]
        snapshot = harness.cost_monitor.snapshot()
        assert snapshot["accumulated_cost_usd"] == pytest.approx(1.8)
        assert snapshot["downgraded_problems"] == 1

    def test_unmapped_difficulty_fails_fast(self, tmp_path, monkeypatch):
        patch_runtimes(monkeypatch, {"vanilla": 0.0})
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy"), problem_payload("p2", "hard")],
            {"easy": "vanilla"},
        )
        with pytest.raises(ValueError, match="not covered"):
            harness.run(use_task_service=True, run_id="run-unmapped")

    def test_selector_requires_task_service_path(self, tmp_path):
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy")],
            {"easy": "vanilla"},
        )
        with pytest.raises(ValueError, match="task service"):
            harness.run()
