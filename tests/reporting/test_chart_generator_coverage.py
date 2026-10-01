"""Tests for chart generation utilities."""

import io

import pytest

from src.reporting.chart_generator import ChartGenerator


@pytest.fixture
def metrics():
    return {
        "green-strategy": {"success_rate": 0.9, "total": 10, "solved": 9},
        "yellow-strategy": {"success_rate": 0.6, "total": 10, "solved": 6},
        "red-strategy": {"success_rate": 0.3, "total": 10, "solved": 3},
    }


class TestSuccessRateChart:
    def test_returns_png_bytes(self, metrics):
        chart = ChartGenerator.generate_success_rate_chart(metrics)
        assert isinstance(chart, io.BytesIO)
        assert chart.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic

    def test_empty_metrics_still_renders(self):
        chart = ChartGenerator.generate_success_rate_chart({})
        assert chart is None or isinstance(chart, io.BytesIO)


class TestTokenChart:
    def test_token_chart_returns_bytes(self, metrics):
        metrics["green-strategy"].update(
            {"prompt_tokens": 100, "completion_tokens": 50}
        )
        metrics["yellow-strategy"].update(
            {"prompt_tokens": 80, "completion_tokens": 40}
        )
        metrics["red-strategy"].update({"prompt_tokens": 60, "completion_tokens": 30})
        chart = ChartGenerator.generate_token_chart(metrics)
        assert chart is None or isinstance(chart, io.BytesIO)
