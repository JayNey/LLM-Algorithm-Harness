"""
Fixed-budget experiment tests (issue #15).

No network access happens in this module: the model is a scripted double
injected at the harness boundary, and the sandbox runs the `host` backend.
Budget and metric assertions are hand-computed against the fixed fixtures.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import ExperimentConfig, LLMConfig, ProblemBudget, SandboxConfig, StrategyConfig

# ============================================================================
# Experiment configuration (task 1)
# ============================================================================


class TestExperimentConfig:
    def _model(self, **overrides):
        values = {
            "provider": "openai",
            "api_key": "env:OPENAI_API_KEY",
            "model": "test-model",
        }
        values.update(overrides)
        return values

    def test_minimal_config_parses_with_defaults(self):
        config = ExperimentConfig(
            dataset_path="data/problems.json",
            models=[self._model()],
            strategies=[{"name": "vanilla", "max_iterations": 1}],
        )
        assert config.repeats == 1
        assert config.output_dir == "./results/experiments"
        assert config.budget is None
        assert config.problem_filters is None

    def test_example_file_parses(self):
        example = Path("experiment.example.json")
        assert example.exists(), "experiment.example.json must ship with the repo"
        payload = json.loads(example.read_text(encoding="utf-8"))
        payload.pop("comment", None)
        config = ExperimentConfig(**payload)
        assert config.budget is not None
        assert config.budget.max_calls == 3
        assert len(config.models) == 1
        assert len(config.strategies) == 2

    def test_empty_models_rejected(self):
        with pytest.raises(ValueError):
            ExperimentConfig(
                dataset_path="data/problems.json",
                models=[],
                strategies=[{"name": "vanilla"}],
            )

    def test_empty_strategies_rejected(self):
        with pytest.raises(ValueError):
            ExperimentConfig(
                dataset_path="data/problems.json",
                models=[self._model()],
                strategies=[],
            )

    def test_repeats_must_be_positive(self):
        with pytest.raises(ValueError):
            ExperimentConfig(
                dataset_path="data/problems.json",
                models=[self._model()],
                strategies=[{"name": "vanilla"}],
                repeats=0,
            )

    def test_budget_validation(self):
        with pytest.raises(ValueError):
            ProblemBudget(max_calls=0)
        with pytest.raises(ValueError):
            ProblemBudget(max_tokens=0)
        with pytest.raises(ValueError):
            ProblemBudget(max_seconds=0)

        budget = ProblemBudget(max_calls=2, max_tokens=1000, max_seconds=30.5)
        assert budget.max_calls == 2
        assert budget.max_tokens == 1000
        assert budget.max_seconds == 30.5

    def test_redacted_dict_hides_api_key(self):
        config = ExperimentConfig(
            dataset_path="data/problems.json",
            models=[self._model(api_key="super-secret-key")],
            strategies=[{"name": "vanilla"}],
        )
        dumped = json.dumps(config.redacted_dict())
        assert "super-secret-key" not in dumped


# ============================================================================
# Budget tracker and budgeted client (task 2)
# ============================================================================


from src.budget import BudgetExhausted, BudgetTracker, BudgetedLLMClient
from src.models import LLMResponse, TokenUsage


def _response(tokens=15, usage_missing=False):
    prompt, completion = 10, 5
    total = 0 if usage_missing else prompt + completion
    return LLMResponse(
        text="```python\ndef solution(x):\n    return x\n```",
        usage=TokenUsage(
            prompt_tokens=prompt if not usage_missing else 0,
            completion_tokens=completion if not usage_missing else 0,
            total_tokens=total,
        ),
        model="fixed-double",
        finish_reason="stop",
        usage_missing=usage_missing,
    )


class TestBudgetTracker:
    def test_call_budget_blocks_after_limit(self):
        tracker = BudgetTracker(ProblemBudget(max_calls=2))
        tracker.begin_problem("p1")
        assert tracker.allow_call()
        tracker.record(_response())
        tracker.record(_response())
        assert not tracker.allow_call()
        assert tracker.stop_reason() == "budget_exhausted: max_calls"

    def test_token_budget_counts_known_usage(self):
        tracker = BudgetTracker(ProblemBudget(max_tokens=20))
        tracker.begin_problem("p1")
        tracker.record(_response(tokens=15))
        assert tracker.allow_call()
        tracker.record(_response(tokens=15))
        assert not tracker.allow_call()
        assert tracker.stop_reason() == "budget_exhausted: max_tokens"
        assert tracker.ledger["p1"]["total_tokens"] == 30

    def test_usage_missing_flags_unsupported_token_budget(self):
        tracker = BudgetTracker(ProblemBudget(max_tokens=100))
        tracker.begin_problem("p1")
        tracker.record(_response(usage_missing=True))
        assert tracker.token_budget_unsupported is True
        # Unknown usage cannot honestly satisfy the token budget
        assert tracker.allow_call() is True
        assert tracker.ledger["p1"]["usage_missing_seen"] is True

    def test_no_budget_always_allows(self):
        tracker = BudgetTracker(None)
        tracker.begin_problem("p1")
        tracker.record(_response())
        assert tracker.allow_call()

    def test_finalize_records_completed_reason(self):
        tracker = BudgetTracker(ProblemBudget(max_calls=5))
        tracker.begin_problem("p1")
        tracker.record(_response())
        tracker.finalize_problem()
        assert tracker.ledger["p1"]["stop_reason"] == "completed"
        assert tracker.ledger["p1"]["calls"] == 1
        assert tracker.ledger["p1"]["elapsed_seconds"] >= 0


class TestBudgetedLLMClient:
    def test_blocks_call_when_budget_exhausted(self):
        inner = MagicMock()
        tracker = BudgetTracker(ProblemBudget(max_calls=1))
        tracker.begin_problem("p1")
        client = BudgetedLLMClient(inner, tracker)
        client.generate("prompt")
        with pytest.raises(BudgetExhausted):
            client.generate("prompt")
        inner.generate.assert_called_once()

    def test_records_successful_calls(self):
        inner = MagicMock()
        inner.generate.return_value = _response()
        tracker = BudgetTracker(ProblemBudget(max_calls=3))
        tracker.begin_problem("p1")
        client = BudgetedLLMClient(inner, tracker)
        client.generate("prompt")
        assert tracker.ledger["p1"]["calls"] == 1
        assert tracker.ledger["p1"]["total_tokens"] == 15

    def test_proxies_inner_attributes(self):
        inner = MagicMock()
        client = BudgetedLLMClient(inner, BudgetTracker(None))
        assert client.anything is inner.anything


# ============================================================================
# Harness budget integration (task 2)
# ============================================================================


WRONG_BUDGET_SOLUTION = "def solution(x):\n    return x + 100"
CORRECT_BUDGET_SOLUTION = "def solution(x):\n    return x + 1"


def _budget_harness(tmp_path, dataset, budget, strategies=None):
    from src.harness import AlgorithmHarness
    from src.models import HarnessConfig, SandboxConfig

    config = HarnessConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        llm_config=LLMConfig(provider="openai", api_key="offline-test-key", model="fixed-double"),
        sandbox_config=SandboxConfig(backend="host"),
        strategies=(
            strategies
            if strategies is not None
            else [{"name": "multi_round_feedback", "max_iterations": 3}]
        ),
    )
    tracker = BudgetTracker(budget)
    return AlgorithmHarness(config, budget_tracker=tracker), tracker


def _offline_dataset(tmp_path, solution_text):
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "budget-1",
                    "title": "Add One",
                    "description": "Return x plus one for the budget regression run.",
                    "difficulty": "easy",
                    "tags": [],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            ]
        ),
        encoding="utf-8",
    )
    return dataset


def _llm_factory(solution_text):
    def factory(config):
        double = MagicMock()
        double.generate.return_value = LLMResponse(
            text=f"```python\n{solution_text}\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )
        return double

    return factory


def test_multi_round_stops_on_call_budget_with_completed_rounds(tmp_path):
    """Round 1 runs; round 2 is refused and the problem ends budget_exhausted."""
    dataset = _offline_dataset(tmp_path, "def solution(x):\n    return x + 100")
    harness, tracker = _budget_harness(tmp_path, dataset, ProblemBudget(max_calls=1))

    with patch("src.harness.LLMClient", side_effect=_llm_factory(WRONG_BUDGET_SOLUTION)):
        harness.run()

    results = harness.get_results("multi_round_feedback")
    assert len(results) == 1
    record = results[0]
    assert record.status == "budget_exhausted"
    assert record.failure_category is None
    # The completed round stays inspectable
    assert len(record.iterations) == 1
    ledger = tracker.ledger["budget-1"]
    assert ledger["calls"] == 1
    assert ledger["stop_reason"] == "budget_exhausted: max_calls"
    assert ledger["total_tokens"] == 15


def test_multi_round_success_needs_no_extra_calls(tmp_path):
    """A first-round success finishes inside a one-call budget as success."""
    dataset = _offline_dataset(tmp_path, "def solution(x):\n    return x + 1")
    harness, tracker = _budget_harness(tmp_path, dataset, ProblemBudget(max_calls=1))

    with patch("src.harness.LLMClient", side_effect=_llm_factory(CORRECT_BUDGET_SOLUTION)):
        harness.run()

    record = harness.get_results("multi_round_feedback")[0]
    assert record.status == "success"
    assert tracker.ledger["budget-1"]["stop_reason"] == "completed"
    assert tracker.ledger["budget-1"]["calls"] == 1


def test_unbudgeted_harness_keeps_baseline_behavior(tmp_path):
    """Without a tracker nothing changes: failure stays wrong_answer."""
    dataset = _offline_dataset(tmp_path, "def solution(x):\n    return x + 100")
    harness, _ = _budget_harness(tmp_path, dataset, None)

    with patch("src.harness.LLMClient", side_effect=_llm_factory(WRONG_BUDGET_SOLUTION)):
        harness.run()

    record = harness.get_results("multi_round_feedback")[0]
    assert record.status == "failed"
    assert record.failure_category == "wrong_answer"


def test_estimate_cost_marks_unknown_pricing(tmp_path):
    """Unknown pricing keeps cost at zero value with explicit unknown flags."""
    from src.models import ExecutionResult

    harness, _ = _budget_harness(tmp_path, tmp_path / "unused.json", None)
    result = ExecutionResult(
        problem_id="p",
        strategy="vanilla",
        generated_code="",
        status="success",
        llm_traces=[
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "total_tokens": 15,
                "pricing_metadata": {
                    "model": "mystery-model",
                    "prompt_price_per_1k": None,
                    "completion_price_per_1k": None,
                    "source": "unknown",
                    "pricing_known": False,
                    "total_cost": None,
                    "usage_known": True,
                },
            }
        ],
    )
    total, meta = harness._estimate_cost([result])
    assert total == 0.0
    assert meta["unknown_pricing"] is True
    assert meta["unknown_usage"] is True


def test_estimate_cost_no_traces_is_unknown_not_fabricated(tmp_path):
    """Traces-less results no longer get the GPT-3.5-style fabricated cost."""
    from src.models import ExecutionResult

    harness, _ = _budget_harness(tmp_path, tmp_path / "unused.json", None)
    result = ExecutionResult(
        problem_id="p",
        strategy="vanilla",
        generated_code="",
        status="success",
        total_tokens=1000,
    )
    total, meta = harness._estimate_cost([result])
    assert total == 0.0
    assert meta["total_tokens"] == 1000
    assert meta["unknown_usage"] is True


# ============================================================================
# Experiment runner and reproducibility metadata (task 3)
# ============================================================================


import hashlib

from src.experiment import ExperimentRunner


def _runner_dataset(tmp_path):
    """Two problems; the first carries hidden cases for formal metrics."""
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "exp-1",
                    "title": "Add One",
                    "description": "Return x plus one for the experiment run.",
                    "difficulty": "easy",
                    "tags": ["math"],
                    "public_test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                    "hidden_test_cases": [{"input": {"x": 2}, "expected_output": 3}],
                },
                {
                    "problem_id": "exp-2",
                    "title": "Add One Again",
                    "description": "Return x plus one for the experiment run.",
                    "difficulty": "medium",
                    "tags": ["math", "basics"],
                    "test_cases": [{"input": {"x": 5}, "expected_output": 6}],
                },
            ]
        ),
        encoding="utf-8",
    )
    return dataset


def _correct_factory():
    def factory(config):
        double = MagicMock()
        double.generate.return_value = LLMResponse(
            text="```python\ndef solution(x):\n    return x + 1\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )
        return double

    return factory


def _runner_config(tmp_path, dataset, **overrides):
    values = dict(
        name="repro-e2e",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "experiments"),
        models=[LLMConfig(provider="openai", api_key="offline-test-key", model="fixed-double")],
        strategies=[
            StrategyConfig(name="vanilla", max_iterations=1),
            StrategyConfig(name="multi_round_feedback", max_iterations=2),
        ],
        repeats=2,
        budget=ProblemBudget(max_calls=2),
        sandbox_config=SandboxConfig(backend="host"),
    )
    values.update(overrides)
    return ExperimentConfig(**values)


def test_runner_executes_all_combinations_with_metadata(tmp_path):
    dataset = _runner_dataset(tmp_path)
    config = _runner_config(tmp_path, dataset)

    with patch("src.harness.LLMClient", side_effect=_correct_factory()):
        exp_dir = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    meta = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))

    # Reproducibility metadata
    assert meta["dataset"]["sha256"] == hashlib.sha256(dataset.read_bytes()).hexdigest()
    assert meta["dataset"]["problem_ids"] == ["exp-1", "exp-2"]
    assert meta["code_version"]["git_commit"]
    assert meta["budget"] == {"max_calls": 2, "max_tokens": None, "max_seconds": None}
    assert meta["pricing_snapshot"]["fixed-double"]["source"] == "unknown"
    assert meta["finished_at"]

    # API key never lands in the metadata
    assert "offline-test-key" not in json.dumps(meta)

    # model x strategy x repeat = 1 x 2 x 2 combinations
    assert len(meta["combinations"]) == 4
    combo_ids = [c["combo_id"] for c in meta["combinations"]]
    assert combo_ids == [
        "fixed-double__vanilla__r1",
        "fixed-double__vanilla__r2",
        "fixed-double__multi_round_feedback__r1",
        "fixed-double__multi_round_feedback__r2",
    ]

    # Per-combination artifacts use the regular run shape
    for combo in meta["combinations"]:
        combo_dir = exp_dir / combo["combo_dir"]
        summary = json.loads((combo_dir / "summary.json").read_text(encoding="utf-8"))
        strategy_name = combo["strategy"]
        assert summary[strategy_name]["total_problems"] == 2
        results = json.loads(
            (combo_dir / f"{strategy_name}_results.json").read_text(encoding="utf-8")
        )
        assert len(results) == 2
        ledger = json.loads((combo_dir / "budget_ledger.json").read_text(encoding="utf-8"))
        assert len(ledger["problems"]) == 2
        for entry in ledger["problems"]:
            assert entry["stop_reason"] == "completed"
            assert entry["total_tokens"] == 15


def test_runner_respects_problem_filters(tmp_path):
    dataset = _runner_dataset(tmp_path)
    config = _runner_config(tmp_path, dataset, repeats=1, problem_filters={"difficulty": "easy"})

    with patch("src.harness.LLMClient", side_effect=_correct_factory()):
        exp_dir = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    meta = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))
    assert meta["dataset"]["problem_ids"] == ["exp-1"]
    summary = json.loads(
        (exp_dir / meta["combinations"][0]["combo_dir"] / "summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["vanilla"]["total_problems"] == 1


# ============================================================================
# Comparison report (task 5)
# ============================================================================


from src.experiment_report import generate_comparison_report


def _report_dataset(tmp_path):
    """exp-1 has hidden cases (formal); exp-2 is sample-only."""
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "exp-1",
                    "title": "Add One",
                    "description": "Return x plus one for the report run.",
                    "difficulty": "easy",
                    "tags": ["math"],
                    "public_test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                    "hidden_test_cases": [{"input": {"x": 2}, "expected_output": 3}],
                },
                {
                    "problem_id": "exp-2",
                    "title": "Add One Again",
                    "description": "Return x plus one for the report run.",
                    "difficulty": "medium",
                    "tags": ["math", "basics"],
                    "test_cases": [{"input": {"x": 5}, "expected_output": 6}],
                },
            ]
        ),
        encoding="utf-8",
    )
    return dataset


def _alternating_factory():
    """Combo 1 (vanilla) is always correct; combo 2 fails then fixes.

    The runner executes combinations sequentially, so the client
    construction order identifies which strategy a double serves.
    """
    construction = {"n": 0}
    call_counter = {"n": 0}

    def _response(text):
        return LLMResponse(
            text=f"```python\n{text}\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )

    def factory(config):
        construction["n"] += 1
        double = MagicMock()
        if construction["n"] % 2 == 1:
            double.generate.return_value = _response("def solution(x):\n    return x + 1")
        else:

            def generate(*args, **kwargs):
                call_counter["n"] += 1
                if call_counter["n"] % 2 == 1:
                    return _response("def solution(x):\n    return x + 100")
                return _response("def solution(x):\n    return x + 1")

            double.generate.side_effect = generate
        return double

    return factory


def _always_wrong_factory():
    def _response(text):
        return LLMResponse(
            text=f"```python\n{text}\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )

    def factory(config):
        double = MagicMock()
        double.generate.return_value = _response("def solution(x):\n    return x + 100")
        return double

    return factory


def test_comparison_report_hand_computed_metrics(tmp_path):
    dataset = _report_dataset(tmp_path)
    config = _runner_config(
        tmp_path,
        dataset,
        repeats=1,
        strategies=[
            StrategyConfig(name="vanilla", max_iterations=1),
            StrategyConfig(name="multi_round_feedback", max_iterations=2),
        ],
    )

    with patch("src.harness.LLMClient", side_effect=_alternating_factory()):
        exp_dir = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    comparison = json.loads((exp_dir / "comparison.json").read_text(encoding="utf-8"))
    assert (exp_dir / "REPORT.md").exists()
    assert (exp_dir / "comparison.csv").exists()
    assert len(comparison["combinations"]) == 2

    vanilla = comparison["combinations"][0]
    assert vanilla["strategy"] == "vanilla"
    assert vanilla["denominator"] == {"total": 2, "completed": 2, "budget_exhausted": 0}
    assert vanilla["solved"] == 2
    assert vanilla["pass_rate_over_total"] == 1.0
    # Only exp-1 has hidden cases: formal rate is 1/1
    assert vanilla["formal"] == {"evaluable": 1, "solved": 1, "rate": 1.0}
    assert vanilla["sample_validation"] == {"validated": 2, "completed": 2, "rate": 1.0}
    # Single-round strategy has no fix opportunities
    assert vanilla["fix_rate"] == {"opportunities": 0, "fixed": 0, "rate": None}
    # 1 call and 15 tokens per problem (hand computed: 2 problems x 15 tokens)
    assert vanilla["actual_consumption"]["avg_calls_per_problem"] == 1
    assert vanilla["actual_consumption"]["avg_tokens_per_problem"] == 15
    # Unknown pricing never reports a dollar figure
    assert vanilla["cost"] == {"total_cost_usd": None, "known": False}
    assert vanilla["by_difficulty"]["easy"] == {"solved": 1, "total": 1, "rate": 1.0}
    assert vanilla["by_tags"]["basics"] == {"solved": 1, "total": 1, "rate": 1.0}

    multi = comparison["combinations"][1]
    assert multi["strategy"] == "multi_round_feedback"
    assert multi["solved"] == 2
    assert multi["denominator"] == {"total": 2, "completed": 2, "budget_exhausted": 0}
    # Both problems failed round 1 and were fixed in round 2
    assert multi["fix_rate"] == {"opportunities": 2, "fixed": 2, "rate": 1.0}
    assert multi["actual_consumption"]["avg_calls_per_problem"] == 2
    assert multi["actual_consumption"]["avg_tokens_per_problem"] == 30

    # Single repeat: explicit no-range note
    agg = comparison["by_model_strategy"][0]
    assert agg["repeats"] == 1
    assert "单次运行" in agg["uncertainty_note"]

    report_md = (exp_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "未知" in report_md  # unknown cost display
    assert "total = completed" in report_md or "总数 = 完成" in report_md

    csv_lines = (exp_dir / "comparison.csv").read_text(encoding="utf-8").strip().splitlines()
    assert len(csv_lines) == 3  # header + 2 combos


def test_comparison_report_budget_exhausted_and_ranges(tmp_path):
    dataset = _report_dataset(tmp_path)
    config = _runner_config(
        tmp_path,
        dataset,
        repeats=2,
        budget=ProblemBudget(max_calls=1),
        strategies=[StrategyConfig(name="multi_round_feedback", max_iterations=3)],
    )

    with patch("src.harness.LLMClient", side_effect=_always_wrong_factory()):
        exp_dir = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    comparison = json.loads((exp_dir / "comparison.json").read_text(encoding="utf-8"))
    assert len(comparison["combinations"]) == 2  # 1 model x 1 strategy x 2 repeats
    for combo in comparison["combinations"]:
        assert combo["denominator"] == {"total": 2, "completed": 0, "budget_exhausted": 2}
        assert combo["solved"] == 0
        assert combo["pass_rate_over_total"] == 0.0
        assert combo["pass_rate_over_completed"] is None
        assert combo["failure_categories"]["budget_exhausted"] == 2
        assert combo["sample_validation"]["rate"] is None

    agg = comparison["by_model_strategy"][0]
    assert agg["repeats"] == 2
    assert "重复 2 次" in agg["uncertainty_note"]
    assert agg["ranges"]["pass_rate_over_total"] == {"min": 0.0, "max": 0.0}

    report_md = (exp_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "预算未完成" in report_md


# ============================================================================
# CLI experiment subcommand (task 6)
# ============================================================================


def _run_main(argv):
    from src.main import main

    exit_code = 0
    with patch("sys.argv", ["main.py"] + argv):
        try:
            main()
        except SystemExit as exc:
            exit_code = exc.code or 0
    return exit_code


def _experiment_config_file(tmp_path, dataset, strategies=None, repeats=1):
    config = tmp_path / "experiment.json"
    payload = {
        "name": "cli-e2e",
        "dataset_path": str(dataset),
        "output_dir": str(tmp_path / "experiments"),
        "repeats": repeats,
        "models": [
            {
                "provider": "openai",
                "api_key": "offline-test-key",
                "model": "fixed-double",
            }
        ],
        "strategies": (
            strategies if strategies is not None else [{"name": "vanilla", "max_iterations": 1}]
        ),
        "sandbox_config": {"backend": "host"},
    }
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def test_cli_experiment_end_to_end(tmp_path, capsys):
    dataset = _report_dataset(tmp_path)
    config_path = _experiment_config_file(tmp_path, dataset)

    with patch("src.harness.LLMClient", side_effect=_correct_factory()):
        exit_code = _run_main(["experiment", "--config", str(config_path)])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Experiment completed" in captured.out
    exp_dirs = list((tmp_path / "experiments").glob("exp-*"))
    assert len(exp_dirs) == 1
    assert (exp_dirs[0] / "REPORT.md").exists()
    assert (exp_dirs[0] / "comparison.json").exists()
    assert (exp_dirs[0] / "comparison.csv").exists()


def test_cli_experiment_rejects_unknown_strategy(tmp_path, capsys):
    dataset = _report_dataset(tmp_path)
    config_path = _experiment_config_file(
        tmp_path, dataset, strategies=[{"name": "no_such_strategy"}]
    )

    exit_code = _run_main(["experiment", "--config", str(config_path)])

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "no_such_strategy" in captured.err


def test_cli_experiment_output_dir_override(tmp_path):
    dataset = _report_dataset(tmp_path)
    config_path = _experiment_config_file(tmp_path, dataset)

    with patch("src.harness.LLMClient", side_effect=_correct_factory()):
        exit_code = _run_main(
            [
                "experiment",
                "--config",
                str(config_path),
                "--output-dir",
                str(tmp_path / "override"),
            ]
        )

    assert exit_code == 0
    assert list((tmp_path / "override").glob("exp-*"))


def test_time_budget_stops_problem(tmp_path):
    """A per-problem max_seconds budget refuses calls once elapsed."""
    tracker = BudgetTracker(ProblemBudget(max_seconds=0.05))
    tracker.begin_problem("p1")
    import time as _time

    _time.sleep(0.06)
    assert tracker.allow_call() is False
    assert tracker.stop_reason() == "budget_exhausted: max_seconds"


def test_runner_rerun_creates_new_directory(tmp_path):
    """The same config reruns into a fresh directory without overwriting."""
    dataset = _runner_dataset(tmp_path)
    config = _runner_config(tmp_path, dataset, repeats=1)

    with patch("src.harness.LLMClient", side_effect=_correct_factory()):
        first = ExperimentRunner(config, pricing_file="nonexistent.json").run()
        second = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    assert first != second
    assert first.exists() and second.exists()
    assert sorted((tmp_path / "experiments").glob("exp-*")) == [first, second]


# ============================================================================
# Model comparison: win-rate matrix, significance, cost-effectiveness (#48)
# ============================================================================


import re

from src.experiment_report import _mcnemar_annotation, build_model_comparison


def _pairwise_dataset(tmp_path, count=8):
    dataset = tmp_path / "problems.json"
    problems = []
    for i in range(1, count + 1):
        problems.append(
            {
                "problem_id": f"pw-{i}",
                "title": f"Problem {i}",
                "description": f"Return x plus one for pairwise problem {i}.",
                "difficulty": "easy" if i % 2 else "medium",
                "tags": ["math"],
                "test_cases": [{"input": {"x": i}, "expected_output": i + 1}],
            }
        )
    dataset.write_text(json.dumps(problems), encoding="utf-8")
    return dataset


def _model_solution(model: str, problem_number: int) -> str:
    if model == "model-a":
        solved = problem_number <= 6
    else:  # model-b solves 1,2,3,7
        solved = problem_number in {1, 2, 3, 7}
    if solved:
        return "def solution(x):\n    return x + 1"
    return "def solution(x):\n    return x + 100"


def _pairwise_factory():
    def factory(config):
        model = config.model
        double = MagicMock()
        double.generate.return_value = None
        double.generate.side_effect = lambda prompt, **kwargs: LLMResponse(
            text="```python\n"
            + _model_solution(model, int(re.search(r"Problem (\d+)", prompt).group(1)))
            + "\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model=model,
            finish_reason="stop",
            # Only model-a carries pricing; model-b stays cost-unknown
            pricing_metadata={
                "model": model,
                "prompt_price_per_1k": 0.001,
                "completion_price_per_1k": 0.002,
                "source": "custom",
                "pricing_known": model == "model-a",
                "usage_known": True,
                "total_cost": 0.00002 if model == "model-a" else None,
            },
        )
        return double

    return factory


def _pricing_known_for_a(tmp_path):
    pricing = tmp_path / "pricing.json"
    pricing.write_text(
        json.dumps({"models": {"model-a": {"prompt": 0.001, "completion": 0.002}}}),
        encoding="utf-8",
    )
    return str(pricing)


def _pairwise_runner(tmp_path, repeats=1, execution="serial"):
    dataset = _pairwise_dataset(tmp_path)
    config = ExperimentConfig(
        name="pairwise",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "experiments"),
        models=[
            LLMConfig(provider="openai", api_key="k", model="model-a"),
            LLMConfig(provider="openai", api_key="k", model="model-b"),
        ],
        strategies=[StrategyConfig(name="vanilla", max_iterations=1)],
        repeats=repeats,
        sandbox_config=SandboxConfig(backend="host"),
        execution=execution,
    )
    return config, dataset


def test_win_rate_matrix_hand_computed(tmp_path):
    config, _ = _pairwise_runner(tmp_path)
    with patch("src.harness.LLMClient", side_effect=_pairwise_factory()):
        exp_dir = ExperimentRunner(config, pricing_file=_pricing_known_for_a(tmp_path)).run()

    comparison = json.loads((exp_dir / "comparison.json").read_text(encoding="utf-8"))
    mc = comparison["model_comparison"]
    strategy = mc["strategies"]["vanilla"]

    row_a = strategy["matrix"][0]
    assert row_a["model"] == "model-a"
    assert row_a["solved"] == 6
    cell = row_a["against"]["model-b"]
    # A-only: pw-4/5/6 (3 wins); B-only: pw-7 (1 loss); same outcome: 4 ties
    assert cell == {"wins": 3, "ties": 4, "losses": 1, "win_rate": 0.375}
    assert cell["wins"] + cell["ties"] + cell["losses"] == 8

    row_b = strategy["matrix"][1]
    assert row_b["solved"] == 4
    assert row_b["against"]["model-a"]["wins"] == 1
    assert row_b["against"]["model-a"]["losses"] == 3

    # Discordant pairs (3, 1): exact McNemar p = 0.625, not significant
    sig = strategy["significance"][0]
    assert (sig["a"], sig["b"]) == ("model-a", "model-b")
    assert sig["discordant_pairs"] == 4
    assert abs(sig["p_value"] - 0.625) < 1e-6
    assert sig["significant"] is False

    # model-a priced, model-b unknown: only model-a is ranked
    assert [entry["model"] for entry in mc["cost_effectiveness"]] == ["model-a"]
    assert mc["cost_unknown_models"] == ["model-b"]


def test_mcnemar_annotation_branches():
    insufficient = _mcnemar_annotation(0, 0)
    assert insufficient["significant"] is None
    assert "样本不足" in insufficient["note"]

    significant = _mcnemar_annotation(6, 0)
    assert significant["significant"] is True
    assert abs(significant["p_value"] - 0.03125) < 1e-6

    small = _mcnemar_annotation(3, 1)
    assert small["significant"] is False
    assert "保守" in small["note"]


def test_budget_exhausted_pairing_counts_as_loss(tmp_path):
    """A problem finished by B but budget-stopped under A counts for B."""
    dataset = _pairwise_dataset(tmp_path, count=2)
    config = ExperimentConfig(
        name="pairwise-budget",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "experiments"),
        models=[LLMConfig(provider="openai", api_key="k", model="model-a")],
        strategies=[StrategyConfig(name="vanilla", max_iterations=1)],
        repeats=1,
        sandbox_config=SandboxConfig(backend="host"),
    )
    with patch("src.harness.LLMClient", side_effect=_pairwise_factory()):
        exp_dir_a = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    # Manually assemble a model-b run that solves pw-1 and budget-stops pw-2,
    # then verify the pairing logic through build_model_comparison
    meta = json.loads((exp_dir_a / "experiment.json").read_text(encoding="utf-8"))
    results_a = json.loads(
        (exp_dir_a / "model-a__vanilla__r1" / "vanilla_results.json").read_text(encoding="utf-8")
    )
    results_b = [
        {"problem_id": "pw-1", "status": "success"},
        {"problem_id": "pw-2", "status": "budget_exhausted"},
    ]
    combos = [
        {
            "combo_id": "model-a__vanilla__r1",
            "model": "model-a",
            "strategy": "vanilla",
            "repeat": 1,
            "solved": 1,
            "cost": {"total_cost_usd": 0.5, "known": True},
        },
        {
            "combo_id": "model-b__vanilla__r1",
            "model": "model-b",
            "strategy": "vanilla",
            "repeat": 1,
            "solved": 1,
            "cost": {"total_cost_usd": None, "known": False},
        },
    ]
    raw = {
        "model-a__vanilla__r1": [
            {"problem_id": r["problem_id"], "status": "failed"} for r in results_a
        ],
        "model-b__vanilla__r1": results_b,
    }
    # Override model-a outcomes: pw-1 solved, pw-2 budget exhausted
    raw["model-a__vanilla__r1"] = [
        {"problem_id": "pw-1", "status": "success"},
        {"problem_id": "pw-2", "status": "budget_exhausted"},
    ]
    meta["dataset"]["problem_ids"] = ["pw-1", "pw-2"]

    mc = build_model_comparison(meta, combos, raw)
    cell = mc["strategies"]["vanilla"]["matrix"][0]["against"]["model-b"]
    # pw-1: both solved (tie); pw-2: both budget-exhausted (tie)
    assert cell == {"wins": 0, "ties": 2, "losses": 0, "win_rate": 0.0}


# ============================================================================
# HTML comparison panel and parallel execution (#48)
# ============================================================================


def test_panel_html_contains_charts_and_matrix(tmp_path):
    config, _ = _pairwise_runner(tmp_path)
    with patch("src.harness.LLMClient", side_effect=_pairwise_factory()):
        exp_dir = ExperimentRunner(config, pricing_file=_pricing_known_for_a(tmp_path)).run()

    panel_path = exp_dir / "panel.html"
    assert panel_path.exists(), "runner must generate panel.html"
    panel = panel_path.read_text(encoding="utf-8")

    # Three chart canvases plus the Chart.js CDN reference
    assert 'id="radar"' in panel and 'id="scatter"' in panel and 'id="bar"' in panel
    assert "cdn.jsdelivr.net/npm/chart.js" in panel

    # Win-rate matrix table rendered with the hand-computed counts
    assert "胜率矩阵 — vanilla" in panel
    assert "3胜 4平 1负" in panel

    # Cost-unknown model-b never enters the scatter payload
    data_match = re.search(
        r'<script id="panel-data" type="application/json">(.*?)</script>', panel, re.DOTALL
    )
    assert data_match, "panel data must be embedded"
    payload = json.loads(data_match.group(1).replace("<\\/", "</"))
    scatter_labels = [point["label"] for point in payload["scatter"]]
    assert scatter_labels == ["model-a × vanilla"]

    # Offline degradation hint ships with the page
    assert "offline-hint" in panel


def test_parallel_execution_matches_serial_structure(tmp_path):
    """Same config under serial and parallel yields identical artifacts."""
    dataset = _pairwise_dataset(tmp_path)
    serial_config = ExperimentConfig(
        name="mode-serial",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "serial"),
        models=[
            LLMConfig(provider="openai", api_key="k", model="model-a"),
            LLMConfig(provider="openai", api_key="k", model="model-b"),
        ],
        strategies=[StrategyConfig(name="vanilla", max_iterations=1)],
        repeats=2,
        sandbox_config=SandboxConfig(backend="host"),
    )
    parallel_config = serial_config.model_copy(
        update={
            "name": "mode-parallel",
            "output_dir": str(tmp_path / "parallel"),
            "execution": "parallel",
            "max_workers": 2,
        }
    )
    with patch("src.harness.LLMClient", side_effect=_pairwise_factory()):
        serial_dir = ExperimentRunner(serial_config, pricing_file="nonexistent.json").run()
        parallel_dir = ExperimentRunner(parallel_config, pricing_file="nonexistent.json").run()

    def _structure(exp_dir):
        meta = json.loads((exp_dir / "experiment.json").read_text(encoding="utf-8"))
        combos = [c["combo_id"] for c in meta["combinations"]]
        panel = (exp_dir / "panel.html").exists()
        comparison = json.loads((exp_dir / "comparison.json").read_text(encoding="utf-8"))
        return combos, panel, sorted(comparison["model_comparison"]["strategies"].keys())

    assert _structure(serial_dir) == _structure(parallel_dir)

    # max_workers bounds concurrency and stays valid at 1
    assert parallel_config.max_workers == 2
    with patch("src.harness.LLMClient", side_effect=_pairwise_factory()):
        single = ExperimentRunner(
            parallel_config.model_copy(
                update={"max_workers": 1, "output_dir": str(tmp_path / "w1")}
            ),
            pricing_file="nonexistent.json",
        ).run()
    assert (single / "panel.html").exists()
