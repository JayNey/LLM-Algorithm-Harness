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

from src.models import ExperimentConfig, LLMConfig, ProblemBudget, StrategyConfig

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
