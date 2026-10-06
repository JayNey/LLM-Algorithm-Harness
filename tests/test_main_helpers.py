"""Tests for small main.py helpers and config defaults."""

import argparse

import pytest

from src.main import (
    apply_cli_overrides,
    create_default_config,
    parse_cost_alert_thresholds,
    positive_float,
    positive_int,
)
from src.models import HarnessConfig, LLMConfig, StrategyConfig


class TestPositiveParsers:
    def test_positive_int(self):
        assert positive_int("3") == 3
        with pytest.raises(argparse.ArgumentTypeError):
            positive_int("0")
        with pytest.raises(ValueError):
            positive_int("abc")

    def test_positive_float(self):
        assert positive_float("0.5") == 0.5
        with pytest.raises(argparse.ArgumentTypeError):
            positive_float("0")
        with pytest.raises(argparse.ArgumentTypeError):
            positive_float("nan")
        with pytest.raises(argparse.ArgumentTypeError):
            positive_float("abc")

    def test_cost_alert_thresholds_sorted_deduped(self):
        assert parse_cost_alert_thresholds("90,50,80") == [50, 80, 90]
        with pytest.raises(argparse.ArgumentTypeError):
            parse_cost_alert_thresholds("0")
        with pytest.raises(argparse.ArgumentTypeError):
            parse_cost_alert_thresholds("101")


class TestCreateDefaultConfig:
    def test_defaults_include_all_strategies(self, tmp_path):
        config = create_default_config(str(tmp_path / "problems.json"), str(tmp_path / "out"))
        assert [s.name for s in config.strategies] == [
            "vanilla",
            "chain_of_thought",
            "multi_round_feedback",
        ]
        assert config.dataset_path == str(tmp_path / "problems.json")
        assert config.sandbox_config.allowed_imports


class TestApplyCliOverridesErrors:
    @staticmethod
    def base_config(strategies=None):
        if strategies is None:
            strategies = [StrategyConfig(name="vanilla")]
        return HarnessConfig(
            dataset_path="data/problems.json",
            llm_config=LLMConfig(provider="openai", api_key="k", model="m"),
            strategies=strategies,
        )

    @staticmethod
    def base_args(**over):
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
            auto_stop_on_budget=False,
            downgrade_on_budget=False,
        )
        defaults.update(over)
        return argparse.Namespace(**defaults)

    def test_strategy_not_enabled_in_config(self):
        with pytest.raises(ValueError, match="not enabled in the configuration"):
            apply_cli_overrides(
                self.base_config(),
                self.base_args(strategy="chain_of_thought"),
            )

    def test_no_valid_strategy_configured(self):
        with pytest.raises(ValueError, match="At least one valid strategy"):
            apply_cli_overrides(
                self.base_config(strategies=[]),
                self.base_args(),
            )
