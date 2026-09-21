"""Behavioral checks for fixed-budget experiments and their exported metrics."""

import json
import subprocess
import sys
from datetime import date

import pytest

from src.experiments import (
    BudgetedLLMClient,
    BudgetExceeded,
    ExperimentConfig,
    ExperimentModel,
    ExperimentRunner,
    GenerationBudget,
    ModelPrice,
)
from src.models import (
    ExecutionResult,
    IterationResult,
    LLMConfig,
    LLMResponse,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
    TokenUsage,
)


class FixedClient:
    def __init__(self, config):
        self.config = config
        self.calls = 0

    def generate(self, prompt, **kwargs):
        self.calls += 1
        if "API Failure" in prompt:
            raise RuntimeError("provider unavailable")
        code = "def solution(x): return 2" if "Overfit" in prompt else "def solution(x): return x + 1"
        return LLMResponse(
            text=f"```python\n{code}\n```",
            model=self.config.model,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            reasoning_tokens=2,
        )


def _dataset(tmp_path, *, all_problems=True):
    records = [
        {
            "problem_id": "correct", "title": "Correct", "description": "Return x plus one.",
            "difficulty": "easy", "tags": ["arithmetic"],
            "public_test_cases": [{"input": {"x": 1}, "expected_output": 2}],
            "hidden_test_cases": [{"input": {"x": 2}, "expected_output": 3}],
        },
        {
            "problem_id": "overfit", "title": "Overfit", "description": "Return x plus one.",
            "difficulty": "medium", "tags": ["arithmetic"],
            "public_test_cases": [{"input": {"x": 1}, "expected_output": 2}],
            "hidden_test_cases": [{"input": {"x": 2}, "expected_output": 3}],
        },
        {
            "problem_id": "api-failure", "title": "API Failure", "description": "Return x plus one.",
            "difficulty": "hard", "tags": ["failure"],
            "public_test_cases": [{"input": {"x": 1}, "expected_output": 2}],
        },
    ]
    path = tmp_path / "problems.json"
    path.write_text(json.dumps(records if all_problems else records[:1]), encoding="utf-8")
    return path


def _config(tmp_path, dataset, *, price=True, repetitions=1):
    return ExperimentConfig(
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "results"),
        models=[ExperimentModel(
            name="small",
            llm_config=LLMConfig(provider="openai", api_key="experiment-secret", model="fixed-model"),
            price=ModelPrice(
                input_per_1k_usd=1, output_per_1k_usd=2,
                source="fixture", as_of=date(2026, 9, 21),
            ) if price else None,
        )],
        strategies=[StrategyConfig(name="vanilla")],
        sandbox_config=SandboxConfig(backend="host"),
        repetitions=repetitions,
        budget=GenerationBudget(max_calls=2, max_total_tokens=100, max_elapsed_seconds=30),
    )


def test_budget_blocks_extra_calls_and_unknown_usage():
    config = LLMConfig(provider="openai", api_key="x", model="fixed-model")
    client = FixedClient(config)
    budgeted = BudgetedLLMClient(client, GenerationBudget(max_calls=1, max_total_tokens=50))
    budgeted.generate("Correct")
    with pytest.raises(BudgetExceeded, match="call_budget_exhausted"):
        budgeted.generate("Correct")
    assert client.calls == 1
    assert budgeted.snapshot()["reasoning_tokens_reported"] == 2
    assert budgeted.snapshot()["total_tokens"] == 15  # reasoning is included in completion

    class MissingUsage(FixedClient):
        def generate(self, prompt, **kwargs):
            self.calls += 1
            return LLMResponse(
                text="answer", model=self.config.model,
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                usage_missing=True,
            )

    missing = MissingUsage(config)
    strict = BudgetedLLMClient(missing, GenerationBudget(max_calls=3, max_total_tokens=50))
    strict.generate("Correct")
    with pytest.raises(BudgetExceeded, match="token_usage_unknown"):
        strict.generate("Correct")
    assert missing.calls == 1
    assert strict.snapshot()["usage_known"] is False

    token_limited = BudgetedLLMClient(FixedClient(config), GenerationBudget(max_calls=3, max_total_tokens=15))
    token_limited.generate("Correct")
    with pytest.raises(BudgetExceeded, match="token_budget_exhausted"):
        token_limited.generate("Correct")
    assert token_limited.calls == 1

    time_limited = BudgetedLLMClient(FixedClient(config), GenerationBudget(max_calls=3, max_elapsed_seconds=1))
    time_limited.started -= 2
    with pytest.raises(BudgetExceeded, match="time_budget_exhausted"):
        time_limited.generate("Correct")
    assert time_limited.calls == 0

    class ExtraUsage(FixedClient):
        def generate(self, prompt, **kwargs):
            self.calls += 1
            return LLMResponse(
                text="answer", model=self.config.model,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=20),
            )

    extra = BudgetedLLMClient(ExtraUsage(config), GenerationBudget(max_calls=2, max_total_tokens=18))
    extra.generate("Correct")
    assert extra.snapshot()["total_tokens"] == 20
    assert extra.snapshot()["unattributed_tokens"] == 5
    assert extra.snapshot()["token_limit_overshot"] is True
    with pytest.raises(BudgetExceeded, match="token_budget_exhausted"):
        extra.generate("Correct")

    class SeparateReasoning(FixedClient):
        def generate(self, prompt, **kwargs):
            self.calls += 1
            return LLMResponse(
                text="answer", model=self.config.model,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
                reasoning_tokens=8,
            )

    separate = BudgetedLLMClient(SeparateReasoning(config), GenerationBudget(max_calls=2))
    separate.generate("Correct")
    assert separate.snapshot()["total_tokens"] == 18
    assert separate.snapshot()["unattributed_tokens"] == 3


def test_experiment_metrics_match_success_overfit_and_api_failure(tmp_path):
    config = _config(tmp_path, _dataset(tmp_path))
    report = ExperimentRunner(config, client_factory=FixedClient).run(run_id="fixed-run")
    summary = report["summaries"]["small:vanilla"]
    assert summary["total"] == 3
    assert summary["sample_passed"] == 2
    assert summary["formal_evaluable"] == 2
    assert summary["formal_passed"] == 1
    assert summary["formal_pass_rate"] == 0.5
    assert summary["failure_counts"]["wrong_answer"] == 1
    assert summary["failure_counts"]["model_error"] == 1
    assert summary["cost_usd"] is None  # API failure has unknown usage
    assert summary["by_difficulty"]["easy"]["formal_passed"] == 1
    assert summary["by_difficulty"]["easy"]["known_tokens"] == 15
    assert summary["by_tag"]["arithmetic"]["total"] == 2
    assert summary["by_tag"]["arithmetic"]["formal_passed"] == 1
    assert report["dataset_fingerprint"]
    assert report["config_fingerprint"]
    assert "experiment-secret" not in json.dumps(report)

    target = tmp_path / "results" / "experiments" / "fixed-run"
    assert (target / "report.json").exists()
    assert (target / "results.csv").exists()
    assert "unknown" in (target / "report.md").read_text(encoding="utf-8")


def test_explicit_price_changes_cost_and_missing_price_stays_unknown(tmp_path):
    dataset = _dataset(tmp_path, all_problems=False)
    config = _config(tmp_path, dataset)
    first = ExperimentRunner(config, client_factory=FixedClient).run(run_id="price-a")
    assert first["summaries"]["small:vanilla"]["cost_usd"] == pytest.approx(0.02)
    config.models[0].price.input_per_1k_usd = 2
    second = ExperimentRunner(config, client_factory=FixedClient).run(run_id="price-b")
    assert second["summaries"]["small:vanilla"]["cost_usd"] == pytest.approx(0.03)
    config.models[0].price = None
    third = ExperimentRunner(config, client_factory=FixedClient).run(run_id="price-unknown")
    assert third["summaries"]["small:vanilla"]["cost_usd"] is None
    assert third["records"][0]["execution"]["llm_traces"][0]["pricing_metadata"]["total_cost"] is None


def test_repetitions_have_distinct_units_and_resume_skips_completed(tmp_path):
    dataset = _dataset(tmp_path, all_problems=False)
    config = _config(tmp_path, dataset, repetitions=2)
    runner = ExperimentRunner(config, client_factory=FixedClient)
    first = runner.run(run_id="repeat-run")
    assert first["summaries"]["small:vanilla"]["total"] == 2
    assert first["summaries"]["small:vanilla"]["repeat_formal_rate_range"] == [1.0, 1.0]
    second = runner.run(run_id="repeat-run", resume=True)
    assert second["summaries"]["small:vanilla"]["total"] == 2
    assert len(runner.service.get("repeat-run").units) == 2


def test_experiment_refuses_changed_dataset_on_resume(tmp_path):
    dataset = _dataset(tmp_path, all_problems=False)
    config = _config(tmp_path, dataset)
    runner = ExperimentRunner(config, client_factory=FixedClient)
    runner.run(run_id="fingerprint-run")
    dataset.write_text(dataset.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="fingerprint"):
        runner.run(run_id="fingerprint-run", resume=True)


def test_environment_credential_change_invalidates_experiment_fingerprint(tmp_path, monkeypatch):
    config = _config(tmp_path, _dataset(tmp_path, all_problems=False))
    config.models[0].llm_config.api_key = "env:EXPERIMENT_KEY"
    monkeypatch.setenv("EXPERIMENT_KEY", "first-value")
    first = config.fingerprint()
    monkeypatch.setenv("EXPERIMENT_KEY", "second-value")
    assert config.fingerprint() != first


def test_repair_rate_counts_only_failed_first_attempts():
    first_failed = SandboxResult(status="failed", all_passed=False)
    later_passed = SandboxResult(status="success", all_passed=True)
    repaired = ExecutionResult(
        problem_id="p", strategy="multi_round_feedback", generated_code="code", status="success",
        iterations=[
            IterationResult(iteration=1, sandbox_result=first_failed),
            IterationResult(iteration=2, sandbox_result=later_passed),
        ],
    )
    first_passed = ExecutionResult(
        problem_id="q", strategy="multi_round_feedback", generated_code="code", status="success",
        iterations=[IterationResult(iteration=1, sandbox_result=later_passed)],
    )
    assert ExperimentRunner._repair_eligible(repaired)
    assert ExperimentRunner._repaired(repaired)
    assert not ExperimentRunner._repair_eligible(first_passed)


def test_multiround_stops_before_second_provider_call_at_budget(tmp_path):
    dataset = _dataset(tmp_path, all_problems=False)
    config = _config(tmp_path, dataset)
    config.strategies = [StrategyConfig(name="multi_round_feedback", max_iterations=3)]
    config.budget = GenerationBudget(max_calls=1)
    calls = []

    class WrongClient(FixedClient):
        def generate(self, prompt, **kwargs):
            calls.append(prompt)
            return LLMResponse(
                text="```python\ndef solution(x): return x + 100\n```",
                model=self.config.model,
                usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            )

    report = ExperimentRunner(config, client_factory=WrongClient).run(run_id="budget-stop")
    record = report["records"][0]
    assert len(calls) == 1
    assert record["status"] == "budget_exhausted"
    assert record["failure_category"] == "budget_exhausted"
    assert record["budget"]["stop_reason"] == "call_budget_exhausted"


def test_experiment_cli_entry_is_available():
    completed = subprocess.run(
        [sys.executable, "-m", "src.main", "experiment", "--help"],
        capture_output=True, text=True, timeout=20,
    )
    assert completed.returncode == 0
    assert "--config" in completed.stdout
    assert "--resume" in completed.stdout
