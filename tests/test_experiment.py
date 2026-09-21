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
