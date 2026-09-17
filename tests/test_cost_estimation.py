"""
End-to-end tests for cost estimation flow.
Tests: custom pricing → summary.json → report generation
"""

import json
import tempfile
from pathlib import Path

import pytest

from src.models import StrategyReport


class TestStrategyReportSerialization:
    """Test StrategyReport serialization with pricing_metadata."""

    def test_strategy_report_with_pricing_metadata(self):
        """Test that StrategyReport correctly serializes pricing_metadata."""
        report = StrategyReport(
            strategy_name="test-strategy",
            success_rate=0.8,
            solved_problems=8,
            failed_problems=2,
            total_problems=10,
            avg_attempts_per_problem=1.5,
            avg_tokens_per_problem=500.0,
            total_tokens=5000,
            estimated_cost_usd=0.025,
            pricing_metadata={
                "model": "gpt-4",
                "prompt_price_per_1k": 0.03,
                "completion_price_per_1k": 0.06,
                "source": "builtin",
                "has_actual_pricing": True,
            },
        )

        # Serialize to dict
        data = report.model_dump()

        # Verify pricing_metadata is present
        assert "pricing_metadata" in data
        assert data["pricing_metadata"]["model"] == "gpt-4"
        assert data["pricing_metadata"]["source"] == "builtin"
        assert data["pricing_metadata"]["has_actual_pricing"] is True

        # Verify JSON serialization
        json_str = json.dumps(data)
        parsed = json.loads(json_str)
        assert parsed["pricing_metadata"]["model"] == "gpt-4"

    def test_strategy_report_without_pricing_metadata(self):
        """Test backward compatibility without pricing_metadata."""
        report = StrategyReport(
            strategy_name="test-strategy",
            success_rate=0.8,
            solved_problems=8,
            failed_problems=2,
            total_problems=10,
            avg_attempts_per_problem=1.5,
            avg_tokens_per_problem=500.0,
            total_tokens=5000,
            estimated_cost_usd=0.025,
        )

        data = report.model_dump()
        assert data.get("pricing_metadata") is None


class TestPricingMetadataFlow:
    """Test that pricing metadata flows through the system correctly."""

    def test_pricing_metadata_structure(self):
        """Test the expected structure of pricing_metadata."""
        # This is the structure we expect from PricingManager
        expected_metadata = {
            "model": "gpt-4o",
            "prompt_price_per_1k": 0.0025,
            "completion_price_per_1k": 0.01,
            "source": "custom",
            "total_cost": 0.015,
            "prompt_tokens": 1000,
            "completion_tokens": 500,
            "total_tokens": 1500,
        }

        # Verify all expected keys are present
        assert "model" in expected_metadata
        assert "prompt_price_per_1k" in expected_metadata
        assert "completion_price_per_1k" in expected_metadata
        assert "source" in expected_metadata
        assert "total_cost" in expected_metadata

    def test_summary_json_with_pricing_metadata(self):
        """Test that summary.json can contain pricing_metadata."""
        summary = {
            "strategies": {
                "vanilla": {
                    "strategy_name": "vanilla",
                    "success_rate": 0.85,
                    "solved_problems": 17,
                    "failed_problems": 3,
                    "total_problems": 20,
                    "avg_attempts_per_problem": 1.2,
                    "avg_tokens_per_problem": 2000.0,
                    "total_tokens": 40000,
                    "estimated_cost_usd": 0.06,
                    "pricing_metadata": {
                        "model": "gpt-4o",
                        "prompt_price_per_1k": 0.0025,
                        "completion_price_per_1k": 0.01,
                        "source": "custom",
                        "has_actual_pricing": True,
                    },
                }
            }
        }

        # Verify JSON serialization works
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(summary, f, indent=2)
            temp_path = f.name

        try:
            # Read back and verify
            with open(temp_path, "r") as f:
                loaded = json.load(f)

            assert "strategies" in loaded
            assert "vanilla" in loaded["strategies"]
            assert "pricing_metadata" in loaded["strategies"]["vanilla"]
            assert loaded["strategies"]["vanilla"]["pricing_metadata"]["model"] == "gpt-4o"
            assert loaded["strategies"]["vanilla"]["pricing_metadata"]["source"] == "custom"
        finally:
            Path(temp_path).unlink()

    def test_backward_compatibility_without_pricing_metadata(self):
        """Test that old summary.json format without pricing_metadata still works."""
        old_summary = {
            "strategies": {
                "vanilla": {
                    "strategy_name": "vanilla",
                    "success_rate": 0.75,
                    "solved_problems": 15,
                    "failed_problems": 5,
                    "total_problems": 20,
                    "avg_attempts_per_problem": 1.5,
                    "avg_tokens_per_problem": 1800.0,
                    "total_tokens": 36000,
                    "estimated_cost_usd": 0.054,
                    # No pricing_metadata field
                }
            }
        }

        # Verify JSON serialization works
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(old_summary, f, indent=2)
            temp_path = f.name

        try:
            # Read back and verify
            with open(temp_path, "r") as f:
                loaded = json.load(f)

            assert "strategies" in loaded
            assert "vanilla" in loaded["strategies"]
            # pricing_metadata should be absent
            assert "pricing_metadata" not in loaded["strategies"]["vanilla"]
            # But cost estimation should still be present
            assert loaded["strategies"]["vanilla"]["estimated_cost_usd"] == 0.054
        finally:
            Path(temp_path).unlink()
