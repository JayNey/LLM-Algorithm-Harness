"""
Tests for PricingManager module.
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.utils.pricing import PricingManager, PricingInfo


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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "models": {
                    "deepseek-chat": {
                        "prompt": 0.0014,
                        "completion": 0.0028
                    },
                    "custom-model": {
                        "prompt": 0.001,
                        "completion": 0.002
                    }
                }
            }, f)
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "models": {
                    "gpt-4": {
                        "prompt": 0.025,
                        "completion": 0.05
                    }
                }
            }, f)
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

            # Test default fallback
            pricing = pm.get_pricing("unknown-model-xyz")
            assert pricing.source == "default"
            assert pricing.prompt_price == PricingManager.DEFAULT_PROMPT_PRICE
            assert pricing.completion_price == PricingManager.DEFAULT_COMPLETION_PRICE
        finally:
            Path(temp_path).unlink()

    def test_prefix_match_priority(self):
        """Test that exact match takes priority over prefix match."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "models": {
                    "gpt-4": {
                        "prompt": 0.03,
                        "completion": 0.06
                    },
                    "gpt-4-turbo": {
                        "prompt": 0.01,
                        "completion": 0.03
                    }
                }
            }, f)
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
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "models": {
                    "custom-model": {
                        "prompt": 0.001,
                        "completion": 0.002
                    }
                }
            }, f)
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

            # Default source
            pricing = pm.get_pricing("unknown-model")
            assert pricing.source == "default"
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
            source="custom"
        )

        result = info.to_dict()
        assert result == {
            "model": "test-model",
            "prompt_price_per_1k": 0.001,
            "completion_price_per_1k": 0.002,
            "source": "custom"
        }
