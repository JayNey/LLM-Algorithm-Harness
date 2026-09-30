"""
Tests for cost-aware strategy selection and run-level budget downgrade (#56b).
"""

import argparse
import json
import threading
from unittest.mock import Mock

import pytest

from src.cost_strategy import (
    CostAwareSelector,
    DifficultyBudgetMonitor,
    RunCostMonitor,
)
from src.harness import AlgorithmHarness
from src.main import (
    SUPPORTED_STRATEGIES,
    apply_cli_overrides,
    parse_cost_alert_thresholds,
    save_results,
)
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
    elif shape == "pricing_unknown":
        traces = [{"pricing_metadata": {"total_cost": cost, "usage_known": True, "pricing_known": False}}]
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
        monitor.add_result(make_result("pricing_unknown", cost=0.2))
        monitor.add_result(make_result("cost_none"))
        monitor.add_result(make_result(cost=float("nan")))
        snapshot = monitor.snapshot()
        assert snapshot["accumulated_cost_usd"] == 0.0
        assert snapshot["unknown_usage_results"] == 5
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


class TestDifficultyBudgetMonitor:
    def test_difficulties_accumulate_independently(self):
        monitor = DifficultyBudgetMonitor({"easy": 1.0, "medium": 2.0})
        monitor.add_result(make_result(cost=0.6), "easy")
        monitor.add_result(make_result(cost=0.6), "easy")
        monitor.add_result(make_result(cost=0.6), "medium")
        assert monitor.over_cap_for("easy") is True
        assert monitor.over_cap_for("medium") is False
        snapshot = monitor.snapshot()
        assert snapshot["easy"]["accumulated_cost_usd"] == pytest.approx(1.2)
        assert snapshot["medium"]["accumulated_cost_usd"] == pytest.approx(0.6)

    def test_unallocated_difficulty_is_ignored(self):
        monitor = DifficultyBudgetMonitor({"easy": 0.5})
        monitor.add_result(make_result(cost=100.0), "hard")
        monitor.add_result(make_result(cost=100.0), None)
        assert monitor.over_cap_for("hard") is False
        assert monitor.over_cap_for(None) is False
        assert set(monitor.snapshot()) == {"easy"}

    def test_downgrade_counting_is_per_difficulty(self):
        monitor = DifficultyBudgetMonitor({"easy": 1.0, "medium": 1.0})
        assert monitor.record_downgrade("easy") is True
        assert monitor.record_downgrade("easy") is False
        assert monitor.record_downgrade("medium") is True
        assert monitor.snapshot()["easy"]["downgraded_problems"] == 2
        assert monitor.snapshot()["medium"]["downgraded_problems"] == 1

    def test_cap_for_reports_configured_budget(self):
        monitor = DifficultyBudgetMonitor({"easy": 0.25})
        assert monitor.cap_for("easy") == 0.25
        assert monitor.cap_for("hard") is None


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
            budget_allocation=None,
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
        with pytest.raises(ValueError, match="requires a difficulty_strategy mapping"):
            apply_cli_overrides(self.make_config(), self.make_args(budget_cap=5.0))

    def test_auto_stop_allows_budget_without_selector(self):
        config = apply_cli_overrides(
            self.make_config(), self.make_args(budget_cap=5.0, auto_stop_on_budget=True)
        )
        assert config.budget_action == "auto_stop"
        assert config.difficulty_strategy is None

    def test_threshold_cli_validation(self):
        assert parse_cost_alert_thresholds("90,50,80") == [50, 80, 90]
        with pytest.raises(argparse.ArgumentTypeError):
            parse_cost_alert_thresholds("50,50")

    def test_parses_budget_allocation(self):
        config = apply_cli_overrides(
            self.make_config(),
            self.make_args(
                difficulty_strategy=[
                    "easy=vanilla",
                    "medium=chain_of_thought",
                    "hard=multi_round_feedback",
                ],
                budget_allocation=["easy=2.5", "medium=5", "hard=0.75"],
            ),
        )
        assert config.budget_allocation == {"easy": 2.5, "medium": 5.0, "hard": 0.75}

    def test_allocation_requires_mapping(self):
        with pytest.raises(ValueError, match="requires a difficulty_strategy mapping"):
            apply_cli_overrides(self.make_config(), self.make_args(budget_allocation=["easy=2.0"]))

    def test_allocation_rejects_duplicate_and_bad_amount(self):
        mapping = ["easy=vanilla", "medium=chain_of_thought", "hard=multi_round_feedback"]
        with pytest.raises(ValueError, match="Duplicate"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(difficulty_strategy=mapping, budget_allocation=["easy=1", "easy=2"]),
            )
        with pytest.raises(ValueError, match="positive"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(difficulty_strategy=mapping, budget_allocation=["easy=-1"]),
            )
        with pytest.raises(ValueError, match="DIFF=USD"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(difficulty_strategy=mapping, budget_allocation=["easy"]),
            )

    def test_allocation_rejects_unknown_difficulty(self):
        with pytest.raises(ValueError, match="Unknown difficulty in budget_allocation"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(
                    difficulty_strategy=["easy=vanilla"],
                    budget_allocation=["extreme=1.0"],
                ),
            )

    def test_allocation_conflicts_with_auto_stop(self):
        with pytest.raises(ValueError, match="downgrade action"):
            apply_cli_overrides(
                self.make_config(),
                self.make_args(
                    difficulty_strategy=["easy=vanilla", "medium=chain_of_thought"],
                    budget_allocation=["easy=1.0"],
                    auto_stop_on_budget=True,
                    budget_cap=5.0,
                ),
            )

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


def make_harness(
    tmp_path, problems, difficulty_strategy, budget_cap_usd=None, budget_allocation=None
):
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
        budget_allocation=budget_allocation,
        max_workers=1,
    )
    return AlgorithmHarness(config)


class TestHarnessCostAwareIntegration:
    def test_auto_stop_pauses_queued_work_writes_cutoff_and_survives_resume(
        self, tmp_path, monkeypatch
    ):
        calls = patch_runtimes(monkeypatch, {"vanilla": 0.6})
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy"), problem_payload("p2", "easy"), problem_payload("p3", "easy")],
            difficulty_strategy=None,
            budget_cap_usd=1.0,
        )
        harness.config.strategies = [StrategyConfig(name="vanilla")]
        harness.config.budget_action = "auto_stop"
        harness.config.max_workers = 3

        reports = harness.run(use_task_service=True, run_id="run-auto-stop")
        assert calls == [("vanilla", "p1"), ("vanilla", "p2")]
        assert harness.task_record.state == "paused"
        assert [unit.status for unit in harness.task_record.units] == ["completed", "completed", "queued"]
        assert reports["vanilla"].total_problems == 2
        assert reports["vanilla"].failed_problems == 0
        assert harness.results["vanilla"][2].status == "cancelled"
        assert harness.cost_monitor.snapshot()["accumulated_cost_usd"] == pytest.approx(1.2)

        save_results(reports, harness.config.output_dir, harness, harness.config)
        run_dir = tmp_path / "results" / "run-auto-stop"
        cutoff = json.loads((run_dir / "cost_cutoff.json").read_text())
        summary = json.loads((run_dir / "summary.json").read_text())
        assert cutoff["queued_units"] == 1
        assert cutoff["completed_units"] == 2
        assert summary["cost_control"]["incomplete"] is True

        resumed = AlgorithmHarness(harness.config)
        resumed.run(use_task_service=True, run_id="run-auto-stop", resume=True)
        assert resumed.task_record.state == "paused"
        assert calls == [("vanilla", "p1"), ("vanilla", "p2")]

    def test_auto_stop_with_selector_pauses_without_downgrading(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch, {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6}
        )
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy"), problem_payload("p2", "medium"), problem_payload("p3", "hard")],
            {"easy": "vanilla", "medium": "chain_of_thought", "hard": "multi_round_feedback"},
            budget_cap_usd=1.0,
        )
        harness.config.budget_action = "auto_stop"
        harness.config.max_workers = 3
        reports = harness.run(use_task_service=True, run_id="run-selector-stop")
        assert calls == [("vanilla", "p1"), ("chain_of_thought", "p2")]
        assert harness.task_record.state == "paused"
        assert harness.task_record.units[2].status == "queued"
        assert reports["cost_aware"].total_problems == 2
        assert reports["cost_aware"].failed_problems == 0
        assert all(not result.cost_downgraded for result in harness.results["cost_aware"])

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
        # Difficulty dimension survives the merged report.
        by_difficulty = reports["cost_aware"].by_difficulty
        assert set(by_difficulty) == {"easy", "hard"}
        assert by_difficulty["easy"]["solved"] == 1
        assert by_difficulty["hard"]["success_rate"] == 1.0
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
        calls = patch_runtimes(monkeypatch, {"vanilla": 0.0})
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy"), problem_payload("p2", "hard")],
            {"easy": "vanilla"},
        )
        with pytest.raises(ValueError, match="not covered"):
            harness.run(use_task_service=True, run_id="run-unmapped")
        # Validation runs before any model call happens.
        assert calls == []

    def test_selector_requires_task_service_path(self, tmp_path):
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy")],
            {"easy": "vanilla"},
        )
        with pytest.raises(ValueError, match="task service"):
            harness.run()

    def test_auto_stop_requires_task_service_path(self, tmp_path):
        harness = make_harness(
            tmp_path, [problem_payload("p1", "easy")], None, budget_cap_usd=1.0
        )
        harness.config.budget_action = "auto_stop"
        with pytest.raises(ValueError, match="task service"):
            harness.run()

    def test_non_selector_run_keeps_per_strategy_reports(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.0, "chain_of_thought": 0.0, "multi_round_feedback": 0.0},
        )
        harness = make_harness(
            tmp_path,
            [problem_payload("p1", "easy")],
            difficulty_strategy=None,
        )
        reports = harness.run(use_task_service=True, run_id="run-plain")

        # Without the selector every configured strategy runs every problem
        # and reports stay keyed per strategy — the pre-change behavior.
        assert set(reports) == {"vanilla", "chain_of_thought", "multi_round_feedback"}
        assert len(calls) == 3
        assert harness.cost_monitor is None

    def test_resume_replays_completed_cost_into_cap(self, tmp_path, monkeypatch):
        patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        problems = [
            problem_payload("p1", "easy"),
            problem_payload("p2", "medium"),
            problem_payload("p3", "hard"),
        ]
        first = make_harness(
            tmp_path,
            problems,
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
            budget_cap_usd=1.0,
        )
        first.run(use_task_service=True, run_id="run-resume")

        replay_calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        resumed = make_harness(
            tmp_path,
            problems,
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
            budget_cap_usd=1.0,
        )
        resumed.run(use_task_service=True, run_id="run-resume", resume=True)

        # Completed problems settle into the ledger before any new work, so
        # the same run cannot spend past the cap across resume cycles.
        assert replay_calls == []
        snapshot = resumed.cost_monitor.snapshot()
        assert snapshot["accumulated_cost_usd"] == pytest.approx(1.8)
        assert resumed.cost_monitor.over_cap

    def test_allocation_downgrades_only_that_difficulty(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        harness = make_harness(
            tmp_path,
            [
                problem_payload("m1", "medium"),
                problem_payload("m2", "medium"),
                problem_payload("m3", "medium"),
                problem_payload("e1", "easy"),
                problem_payload("h1", "hard"),
            ],
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
            budget_allocation={"medium": 1.0},
        )
        reports = harness.run(use_task_service=True, run_id="run-alloc")

        # medium budget (1.0) exhausts after m1+m2; m3 downgrades to the
        # cheapest mapped strategy while easy/hard stay on their mapping.
        assert calls == [
            ("chain_of_thought", "m1"),
            ("chain_of_thought", "m2"),
            ("vanilla", "m3"),
            ("vanilla", "e1"),
            ("multi_round_feedback", "h1"),
        ]
        results = {r.problem_id: r for r in harness.results["cost_aware"]}
        assert results["m3"].cost_downgraded is True
        assert results["m2"].cost_downgraded is False
        assert results["e1"].cost_downgraded is False
        assert results["h1"].cost_downgraded is False
        snapshot = harness.budget_allocation_monitor.snapshot()
        assert snapshot["medium"]["accumulated_cost_usd"] == pytest.approx(1.8)
        assert snapshot["medium"]["downgraded_problems"] == 1
        assert "easy" not in snapshot and "hard" not in snapshot
        by_difficulty = reports["cost_aware"].by_difficulty
        assert by_difficulty["medium"]["cost_usd"] == pytest.approx(1.8)
        assert by_difficulty["easy"]["cost_usd"] == pytest.approx(0.6)
        assert by_difficulty["hard"]["cost_usd"] == pytest.approx(0.6)

    def test_global_cap_downgrades_across_difficulties_with_allocation(self, tmp_path, monkeypatch):
        calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        harness = make_harness(
            tmp_path,
            [
                problem_payload("e1", "easy"),
                problem_payload("m1", "medium"),
                problem_payload("m2", "medium"),
            ],
            {
                "easy": "vanilla",
                "medium": "chain_of_thought",
                "hard": "multi_round_feedback",
            },
            budget_cap_usd=0.9,
            budget_allocation={"medium": 100.0},
        )
        harness.run(use_task_service=True, run_id="run-global-alloc")

        # Global cap (0.9) is exhausted after e1+m1; m2 downgrades even
        # though the medium budget (100.0) is untouched.
        assert calls == [("vanilla", "e1"), ("chain_of_thought", "m1"), ("vanilla", "m2")]
        results = {r.problem_id: r for r in harness.results["cost_aware"]}
        assert results["m2"].cost_downgraded is True
        assert harness.budget_allocation_monitor.snapshot()["medium"]["downgraded_problems"] == 1

    def test_resume_replays_into_difficulty_budgets(self, tmp_path, monkeypatch):
        patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        problems = [
            problem_payload("m1", "medium"),
            problem_payload("m2", "medium"),
            problem_payload("e1", "easy"),
        ]
        mapping = {
            "easy": "vanilla",
            "medium": "chain_of_thought",
            "hard": "multi_round_feedback",
        }
        first = make_harness(tmp_path, problems, mapping, budget_allocation={"medium": 1.0})
        first.run(use_task_service=True, run_id="run-alloc-resume")

        replay_calls = patch_runtimes(
            monkeypatch,
            {"vanilla": 0.6, "chain_of_thought": 0.6, "multi_round_feedback": 0.6},
        )
        resumed = make_harness(tmp_path, problems, mapping, budget_allocation={"medium": 1.0})
        resumed.run(use_task_service=True, run_id="run-alloc-resume", resume=True)

        assert replay_calls == []
        snapshot = resumed.budget_allocation_monitor.snapshot()
        assert snapshot["medium"]["accumulated_cost_usd"] == pytest.approx(1.2)
        assert resumed.budget_allocation_monitor.over_cap_for("medium") is True
        assert resumed.budget_allocation_monitor.over_cap_for("easy") is False
