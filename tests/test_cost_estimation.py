"""
End-to-end tests for cost estimation flow.
Tests: custom pricing → summary.json → report generation
"""

import json
import tempfile
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    LLMResponse,
    Problem,
    StrategyReport,
    TestCase,
)
from src.reporting.html_generator import HTMLGenerator
from src.reporting.markdown_generator import MarkdownGenerator
from src.utils.pricing import PricingManager


class TestEndToEndCostEstimation:
    """Test end-to-end cost estimation with custom pricing."""

    def test_custom_pricing_to_summary_json(self):
        """Test that custom pricing flows through to summary.json."""
        # Create custom pricing file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(
                {
                    "models": {
                        "test-model": {
                            "prompt": 0.005,
                            "completion": 0.015,
                        }
                    }
                },
                f,
            )
            pricing_file = f.name

        try:
            # Create LLMClient with custom pricing
            config = Mock()
            config.provider = "openai"
            config.model = "test-model"
            config.api_key = "test-key"
            config.temperature = 0.7
            config.max_tokens = 1000
            config.base_url = None

            client = LLMClient(config, pricing_file=pricing_file)

            # Estimate cost
            cost, metadata = client.estimate_cost(1000, 500)

            # Verify metadata has custom pricing
            assert metadata["source"] == "custom"
            assert metadata["prompt_price_per_1k"] == 0.005
            assert metadata["completion_price_per_1k"] == 0.015
            assert metadata["model"] == "test-model"

            # Verify cost calculation
            expected_cost = (1000 / 1000 * 0.005) + (500 / 1000 * 0.015)
            assert abs(cost - expected_cost) < 0.0001

        finally:
            Path(pricing_file).unlink()

    def test_builtin_pricing_to_summary_json(self):
        """Test that built-in pricing is tracked correctly."""
        config = Mock()
        config.provider = "openai"
        config.model = "gpt-4"
        config.api_key = "test-key"
        config.temperature = 0.7
        config.max_tokens = 1000
        config.base_url = None

        client = LLMClient(config)
        cost, metadata = client.estimate_cost(1000, 500)

        # Verify metadata has builtin source
        assert metadata["source"] == "builtin"
        assert metadata["model"] == "gpt-4"
        assert metadata["prompt_price_per_1k"] > 0
        assert metadata["completion_price_per_1k"] > 0

    def test_default_pricing_warning(self):
        """Test that unknown models generate warnings."""
        config = Mock()
        config.provider = "openai"
        config.model = "unknown-future-model"
        config.api_key = "test-key"
        config.temperature = 0.7
        config.max_tokens = 1000
        config.base_url = None

        with patch("src.llm_client.logger") as mock_logger:
            client = LLMClient(config)
            cost, metadata = client.estimate_cost(1000, 500)

            # Verify warning was logged
            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "unknown_model_pricing" in str(call_args)

            # Verify metadata has default source
            assert metadata["source"] == "default"


class TestStrategyReportSerialization:
    """Test StrategyReport serialization with pricing metadata."""

    def test_strategy_report_with_pricing_metadata(self):
        """Test that StrategyReport correctly serializes pricing_metadata."""
        report = StrategyReport(
            strategy_name="test-strategy",
            success_rate=0.8,
            solved_problems=8,
            total_problems=10,
            avg_attempts_per_problem=1.5,
            avg_tokens_per_problem=500.0,
            avg_time_per_problem=2.5,
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
            total_problems=10,
            avg_attempts_per_problem=1.5,
            avg_tokens_per_problem=500.0,
            avg_time_per_problem=2.5,
            total_tokens=5000,
            estimated_cost_usd=0.025,
        )

        data = report.model_dump()
        assert data.get("pricing_metadata") is None


class TestReportGenerationWithHistoricalPricing:
    """Test report generation uses historical pricing from summary.json."""

    def test_html_report_with_pricing_metadata(self):
        """Test HTML report uses pricing_metadata from summary."""
        metrics = {
            "test-strategy": {
                "success_rate": 0.8,
                "solved_problems": 8,
                "total_problems": 10,
                "avg_tokens_per_problem": 500,
                "avg_time_per_problem": 2.5,
                "estimated_cost_usd": 0.025,
                "pricing_metadata": {
                    "model": "gpt-4",
                    "prompt_price_per_1k": 0.03,
                    "completion_price_per_1k": 0.06,
                    "source": "custom",
                    "has_actual_pricing": True,
                },
            }
        }

        results = {"test-strategy": []}
        config = {"model": "gpt-4"}

        html = HTMLGenerator.generate(
            metrics=metrics,
            results=results,
            output_path=None,
            include_charts=False,
            config=config,
        )

        # Verify HTML contains cost information
        assert "$0.0250" in html or "0.025" in html
        # Verify pricing source is mentioned
        assert "自定义配置" in html or "custom" in html.lower()

    def test_markdown_report_with_pricing_metadata(self):
        """Test Markdown report uses pricing_metadata from summary."""
        metrics = {
            "test-strategy": {
                "success_rate": 0.8,
                "solved_problems": 8,
                "total_problems": 10,
                "avg_tokens_per_problem": 500,
                "avg_time_per_problem": 2.5,
                "estimated_cost_usd": 0.015,
                "pricing_metadata": {
                    "model": "claude-3-haiku",
                    "prompt_price_per_1k": 0.00025,
                    "completion_price_per_1k": 0.00125,
                    "source": "builtin",
                    "has_actual_pricing": True,
                },
            }
        }

        results = {"test-strategy": []}
        config = {"model": "claude-3-haiku"}

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", delete=False
        ) as f:
            output_path = f.name

        try:
            MarkdownGenerator.generate(
                metrics=metrics,
                results=results,
                output_path=output_path,
                config=config,
            )

            # Read generated markdown
            with open(output_path, "r", encoding="utf-8") as f:
                content = f.read()

            # Verify cost column exists
            assert "Est. Cost (USD)" in content or "estimated_cost" in content.lower()
            # Verify pricing source information
            assert "内置定价" in content or "builtin" in content.lower()

        finally:
            Path(output_path).unlink()

    def test_report_fallback_without_pricing_metadata(self):
        """Test reports handle missing pricing_metadata gracefully."""
        # Old format without pricing_metadata
        metrics = {
            "test-strategy": {
                "success_rate": 0.8,
                "solved_problems": 8,
                "total_problems": 10,
                "avg_tokens_per_problem": 500,
                "avg_time_per_problem": 2.5,
                "estimated_cost_usd": 0.025,
                # No pricing_metadata
            }
        }

        results = {"test-strategy": []}
        config = {"model": "gpt-4"}

        # Should not raise error
        html = HTMLGenerator.generate(
            metrics=metrics,
            results=results,
            output_path=None,
            include_charts=False,
            config=config,
        )

        # Should contain warning about missing historical pricing
        assert "历史数据不可用" in html or "当前配置" in html
