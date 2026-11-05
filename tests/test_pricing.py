"""
Tests for PricingManager module.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.pricing import PricingInfo, PricingManager


class TestBuiltinPricing:
    """Test built-in pricing functionality."""

    def test_builtin_pricing_models(self):
        """Verify all built-in models are available."""
        # Use a non-existent file path to ensure builtin pricing is used
        pm = PricingManager(pricing_file="non_existent_pricing.json")

        # Test that built-in models exist
        expected_models = [
            "gpt-3.5-turbo",
            "gpt-4",
            "gpt-4-turbo",
            "gpt-4o",
            "claude-3-haiku",
            "claude-3-sonnet",
            "claude-3-opus",
            "claude-3-5-sonnet",
            "claude-3-5-haiku",
        ]

        for model in expected_models:
            pricing = pm.get_pricing(model)
            assert pricing.source == "builtin"
            assert pricing.prompt_price > 0
            assert pricing.completion_price > 0
            assert pricing.model == model


class TestCustomPricing:
    """Test custom pricing file loading."""

    def test_load_custom_pricing(self):
        """Test loading custom pricing from file."""
        # Create temporary pricing file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "models": {
                        "deepseek-chat": {"prompt": 0.0014, "completion": 0.0028},
                        "custom-model": {"prompt": 0.001, "completion": 0.002},
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)

            # Test custom model pricing
            pricing = pm.get_pricing("deepseek-chat")
            assert pricing.source == "custom"
            assert pricing.prompt_price == 0.0014
            assert pricing.completion_price == 0.0028

            pricing = pm.get_pricing("custom-model")
            assert pricing.source == "custom"
            assert pricing.prompt_price == 0.001
            assert pricing.completion_price == 0.002
        finally:
            Path(temp_path).unlink()

    def test_file_not_exists_fallback(self):
        """Test fallback when pricing file doesn't exist."""
        pm = PricingManager(pricing_file="nonexistent.json")

        # Should fall back to built-in
        pricing = pm.get_pricing("gpt-4")
        assert pricing.source == "builtin"

    def test_invalid_json_fallback(self):
        """Test fallback when JSON is invalid."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{ invalid json }")
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)

            # Should fall back to built-in
            pricing = pm.get_pricing("gpt-4")
            assert pricing.source == "builtin"
        finally:
            Path(temp_path).unlink()


class TestModelMatching:
    """Test model matching strategies."""

    def test_model_matching_strategy(self):
        """Test exact match, prefix match, and default fallback."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"models": {"gpt-4": {"prompt": 0.025, "completion": 0.05}}}, f)
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)

            # Test exact match in custom
            pricing = pm.get_pricing("gpt-4")
            assert pricing.source == "custom"
            assert pricing.prompt_price == 0.025

            # Test prefix match in custom
            pricing = pm.get_pricing("gpt-4-0613")
            assert pricing.source == "custom"
            assert pricing.prompt_price == 0.025

            # Test exact match in builtin
            pricing = pm.get_pricing("claude-3-opus")
            assert pricing.source == "builtin"

            # Test prefix match in builtin
            pricing = pm.get_pricing("claude-3-opus-20240229")
            assert pricing.source == "builtin"
            assert pricing.model == "claude-3-opus-20240229"

            # Unknown models are marked, never converted with default prices
            pricing = pm.get_pricing("unknown-model-xyz")
            assert pricing.source == "unknown"
            assert pricing.pricing_known is False
            assert pricing.prompt_price is None
            assert pricing.completion_price is None
        finally:
            Path(temp_path).unlink()

    def test_prefix_match_priority(self):
        """Test that exact match takes priority over prefix match."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "models": {
                        "gpt-4": {"prompt": 0.03, "completion": 0.06},
                        "gpt-4-turbo": {"prompt": 0.01, "completion": 0.03},
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)

            # Exact match should be used
            pricing = pm.get_pricing("gpt-4-turbo")
            assert pricing.prompt_price == 0.01

            # Prefix match should fall back to "gpt-4"
            pricing = pm.get_pricing("gpt-4-0613")
            assert pricing.prompt_price == 0.03
        finally:
            Path(temp_path).unlink()


class TestPricingSourceTracking:
    """Test pricing source tracking."""

    def test_pricing_source_tracking(self):
        """Test that pricing source is correctly tracked."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"models": {"custom-model": {"prompt": 0.001, "completion": 0.002}}}, f)
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)

            # Custom source
            pricing = pm.get_pricing("custom-model")
            assert pricing.source == "custom"
            pricing_dict = pricing.to_dict()
            assert pricing_dict["source"] == "custom"
            assert "model" in pricing_dict
            assert "prompt_price_per_1k" in pricing_dict
            assert "completion_price_per_1k" in pricing_dict

            # Builtin source
            pricing = pm.get_pricing("gpt-4")
            assert pricing.source == "builtin"

            # Unknown pricing is marked explicitly
            pricing = pm.get_pricing("unknown-model")
            assert pricing.source == "unknown"
            assert pricing.pricing_known is False
        finally:
            Path(temp_path).unlink()


class TestPricingInfo:
    """Test PricingInfo data class."""

    def test_pricing_info_to_dict(self):
        """Test PricingInfo serialization."""
        info = PricingInfo(
            model="test-model",
            prompt_price=0.001,
            completion_price=0.002,
            source="custom",
            as_of="2026-09-21",
        )

        result = info.to_dict()
        assert result == {
            "model": "test-model",
            "prompt_price_per_1k": 0.001,
            "completion_price_per_1k": 0.002,
            "source": "custom",
            "as_of": "2026-09-21",
            "pricing_known": True,
        }


class TestUnknownPricingAndFormats:
    """Unknown-model marking and alternate pricing file key styles (issue #15)."""

    def test_long_key_format_and_as_of(self):
        """The documented example format (prompt_price_per_1k) must load."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "models": {
                        "qwen2.5-7b": {
                            "prompt_price_per_1k": 0.00015,
                            "completion_price_per_1k": 0.0006,
                            "as_of": "2026-09-21",
                        }
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)
            pricing = pm.get_pricing("qwen2.5-7b")
            assert pricing.source == "custom"
            assert pricing.prompt_price == 0.00015
            assert pricing.completion_price == 0.0006
            assert pricing.as_of == "2026-09-21"
        finally:
            Path(temp_path).unlink()

    def test_entry_without_prices_is_skipped(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump(
                {
                    "models": {
                        "broken-entry": {"prompt_price_per_1k": 0.001},
                        "valid-entry": {"prompt": 0.001, "completion": 0.002},
                    }
                },
                f,
            )
            temp_path = f.name

        try:
            pm = PricingManager(pricing_file=temp_path)
            assert pm.get_pricing("valid-entry").source == "custom"
            assert pm.get_pricing("broken-entry").source == "unknown"
        finally:
            Path(temp_path).unlink()

    def test_unknown_model_marks_pricing_unknown(self):
        pm = PricingManager(pricing_file="nonexistent.json")
        pricing = pm.get_pricing("totally-unknown-model")
        assert pricing.source == "unknown"
        assert pricing.pricing_known is False
        assert pricing.prompt_price is None
        assert pricing.completion_price is None
        assert pricing.as_of is None


class TestLongestBuiltinPrefix:
    """Issue #351: a broad family must never shadow a more specific one."""

    @pytest.mark.parametrize("order", ["original", "reversed", "rotated"])
    @pytest.mark.parametrize(
        "model,prompt,completion",
        [
            ("gpt-4", 0.03, 0.06),
            ("gpt-4-0613", 0.03, 0.06),
            ("gpt-4o", 0.005, 0.015),
            ("gpt-4o-2024-08-06", 0.005, 0.015),
            ("gpt-4o-mini", 0.005, 0.015),
            ("gpt-4-turbo", 0.01, 0.03),
            ("gpt-4-turbo-2024-04-09", 0.01, 0.03),
            ("claude-3-5-haiku-20241022", 0.001, 0.005),
        ],
    )
    def test_family_selection_independent_of_insertion_order(
        self, tmp_path, monkeypatch, order, model, prompt, completion
    ):
        entries = list(PricingManager.BUILTIN_PRICING.items())
        if order == "reversed":
            entries.reverse()
        elif order == "rotated":
            entries = entries[2:] + entries[:2]
        monkeypatch.setattr(PricingManager, "BUILTIN_PRICING", dict(entries))
        manager = PricingManager(str(tmp_path / "absent.json"))
        pricing = manager.get_pricing(model)
        assert pricing.model == model
        assert pricing.source == "builtin"
        assert (pricing.prompt_price, pricing.completion_price) == (prompt, completion)

    @pytest.mark.parametrize(
        "model,override,source,price",
        [
            ("gpt-4o-2024-08-06", True, "override", 0.9),
            ("gpt-4o-2024-08-06", False, "custom", 0.3),
            ("gpt-4o-mini", False, "custom", 0.2),
            ("gpt-4-turbo", False, "custom", 0.1),
        ],
    )
    def test_source_and_exact_precedence(self, tmp_path, model, override, source, price):
        manager = PricingManager(str(tmp_path / "absent.json"))
        manager.custom_pricing = {
            "gpt-4": {"prompt": 0.1, "completion": 0.1},
            "gpt-4o": {"prompt": 0.2, "completion": 0.2},
            "gpt-4o-2024-08-06": {"prompt": 0.3, "completion": 0.3},
        }
        # A family override must not act as a prefix override.
        manager.overrides["gpt-4o"] = PricingInfo("gpt-4o", 0.8, 0.8, "override")
        if override:
            manager.overrides[model] = PricingInfo(model, 0.9, 0.9, "override")
        pricing = manager.get_pricing(model)
        assert pricing.source == source
        assert (pricing.prompt_price, pricing.completion_price) == (price, price)

    @pytest.mark.parametrize(
        "family,snapshot,expected_cost",
        [
            ("gpt-4o", "gpt-4o-2024-08-06", 0.02),
            ("gpt-4-turbo", "gpt-4-turbo-2024-04-09", 0.04),
        ],
    )
    def test_response_cost_reaches_budget_monitor(self, tmp_path, family, snapshot, expected_cost):
        from src.cost_strategy import RunCostMonitor
        from src.llm_client import LLMClient
        from src.models import CacheConfig, ExecutionResult, LLMConfig

        config = LLMConfig(
            provider="openai",
            api_key="offline-test",
            model=family,
            cache=CacheConfig(enabled=False),
        )
        # Replace only the external provider; pricing and budget consumers remain real.
        with patch("src.llm_client.OpenAI") as sdk:
            sdk.return_value.chat.completions.create.return_value = {
                "model": snapshot,
                "choices": [{"message": {"content": "pass"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1000, "completion_tokens": 1000, "total_tokens": 2000},
            }
            client = LLMClient(config)
            client.pricing_manager = PricingManager(str(tmp_path / "absent.json"))
            response = client.generate("offline pricing regression")
        metadata = response.pricing_metadata
        assert response.model == snapshot
        assert metadata["source"] == "builtin"
        assert metadata["pricing_known"] is True
        assert metadata["total_cost"] == pytest.approx(expected_cost)
        assert client.estimate_cost(response.usage) == pytest.approx(expected_cost)
        result = ExecutionResult(
            problem_id="pricing-regression",
            strategy="vanilla",
            generated_code="pass",
            status="success",
            llm_traces=[{**response.usage.model_dump(), "pricing_metadata": metadata}],
        )
        monitor = RunCostMonitor(budget_cap_usd=0.05)
        monitor.add_result(result)
        assert float(monitor.accumulated_cost) == pytest.approx(expected_cost)
        assert monitor.over_cap is False
        monitor.add_result(result)
        monitor.add_result(result)
        assert float(monitor.accumulated_cost) == pytest.approx(expected_cost * 3)
        assert monitor.over_cap is True
