"""Offline tests for stratified prompt A/B testing."""

import json
import subprocess
import sys
from argparse import Namespace

import pytest

from src.ab_testing import (
    ABTestConfig,
    ABTestRunner,
    PromptVariant,
    _proportion_ci,
    stratified_assign,
)
from src.llm_client import LLMResponse
from src.models import LLMConfig, Problem, SandboxConfig, StrategyConfig, TokenUsage


class FixedClient:
    def __init__(self, config):
        self.config = config

    def generate(self, prompt, **kwargs):
        if "treatment" in (kwargs.get("system_prompt") or ""):
            code = "def solution(x): return x + 1"
        else:
            code = "def solution(x): return x + 100"
        return LLMResponse(
            text=f"```python\n{code}\n```",
            model=self.config.model,
            usage=TokenUsage(prompt_tokens=4, completion_tokens=6, total_tokens=10),
        )


def _dataset(tmp_path):
    path = tmp_path / "problems.json"
    path.write_text(json.dumps([
        {
            "problem_id": f"p{i}", "title": f"P{i}", "description": "Return x plus one.",
            "difficulty": "easy" if i < 3 else "hard", "tags": ["array"],
            "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
        }
        for i in range(6)
    ]), encoding="utf-8")
    return path


def _config(tmp_path, dataset):
    return ABTestConfig(
        name="prompt-ab",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "ab-results"),
        model=LLMConfig(provider="openai", api_key="secret", model="fixed"),
        strategy=StrategyConfig(name="vanilla"),
        prompt_variants=[
            PromptVariant(id="baseline", description="baseline", system_prompt="baseline"),
            PromptVariant(id="treatment", description="treatment", system_prompt="treatment"),
        ],
        baseline_id="baseline",
        seed=7,
        sandbox_config=SandboxConfig(backend="host"),
    )


def test_stratified_assignment_is_reproducible_and_balanced():
    problems = [
        Problem(problem_id=f"p{i}", title=f"P{i}", description="A sufficiently long problem description.", difficulty="easy", tags=["array"], test_cases=[{"input": {"x": 1}, "expected_output": 1}])
        for i in range(6)
    ]
    variants = [PromptVariant(id="a"), PromptVariant(id="b")]
    first = stratified_assign(problems, variants, seed=10)
    assert first == stratified_assign(problems, variants, seed=10)
    assert list(first.values()).count("a") == 3
    assert list(first.values()).count("b") == 3


def test_confidence_interval_has_explicit_difference():
    ci = _proportion_ci(1, 4, 3, 4)
    assert ci["difference"] == 0.5
    assert ci["lower"] < ci["difference"] < ci["upper"]


def test_runner_generates_report_csv_markdown_and_statistics(tmp_path):
    config = _config(tmp_path, _dataset(tmp_path))
    output = ABTestRunner(config, client_factory=FixedClient).run()
    report = json.loads((output / "ab_test.json").read_text(encoding="utf-8"))
    assert report["baseline_id"] == "baseline"
    assert report["treatment_id"] == "treatment"
    assert report["balance"]
    assert report["comparison"]["sample"]["ci95"]["difference"] is not None
    assert "p_value" in report["comparison"]["statistics"]
    assert (output / "results.csv").exists()
    assert (output / "REPORT.md").exists()
    assert "baseline" in (output / "REPORT.md").read_text(encoding="utf-8")


def test_ab_test_cli_help_is_available():
    completed = subprocess.run(
        [sys.executable, "-m", "src.main", "ab-test", "--help"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert completed.returncode == 0
    assert "--config" in completed.stdout


def test_ab_config_rejects_duplicate_or_unknown_baseline(tmp_path):
    dataset = _dataset(tmp_path)
    base = {
        "dataset_path": str(dataset),
        "model": {"provider": "openai", "api_key": "x", "model": "m"},
        "strategy": {"name": "vanilla"},
        "prompt_variants": [{"id": "a"}, {"id": "a"}],
    }
    with pytest.raises(ValueError, match="unique"):
        ABTestConfig(**base)
    base["prompt_variants"] = [{"id": "a"}, {"id": "b"}]
    base["baseline_id"] = "missing"
    with pytest.raises(ValueError, match="baseline"):
        ABTestConfig(**base)


def test_ab_command_dispatches_from_main_parser(monkeypatch, tmp_path):
    import src.main as main_module

    monkeypatch.setattr(main_module, "run_ab_test_command", lambda args: 0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "ab-test", "--config", str(tmp_path / "ab.json")],
    )
    with pytest.raises(SystemExit) as exc:
        main_module.main()
    assert exc.value.code == 0


def test_ab_command_executes_with_config_and_output_override(monkeypatch, tmp_path, capsys):
    import src.ab_testing as ab_module
    from src.main import run_ab_test_command

    config_path = tmp_path / "ab.json"
    config_path.write_text(json.dumps({
        "dataset_path": str(_dataset(tmp_path)),
        "model": {"provider": "openai", "api_key": "x", "model": "fixed"},
        "strategy": {"name": "vanilla"},
        "prompt_variants": [{"id": "a"}, {"id": "b"}],
    }), encoding="utf-8")

    class DummyRunner:
        def __init__(self, config):
            self.config = config

        def run(self):
            return tmp_path / "ab-out"

    monkeypatch.setattr(ab_module, "ABTestRunner", DummyRunner)
    result = run_ab_test_command(Namespace(config=str(config_path), output_dir=str(tmp_path / "override"), log_format="console"))
    assert result == 0
    assert "A/B test completed" in capsys.readouterr().out
