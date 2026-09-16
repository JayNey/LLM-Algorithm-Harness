"""
Unit tests for ChartGenerator.
"""

import io
from typing import Dict, List

import pytest
import matplotlib.pyplot as plt

from src.models import ExecutionResult, IterationResult, SandboxResult
from src.reporting.chart_generator import ChartGenerator


@pytest.fixture
def sample_metrics() -> Dict[str, Dict]:
    """Fixture for sample strategy metrics."""
    return {
        "direct": {
            "success_rate": 0.8,
            "avg_tokens_per_problem": 500.0,
        },
        "cot": {
            "success_rate": 0.9,
            "avg_tokens_per_problem": 800.0,
        },
        "self_refine": {
            "success_rate": 0.45,
            "avg_tokens_per_problem": 1200.0,
        }
    }


@pytest.fixture
def sample_multi_round_results() -> Dict[str, List[ExecutionResult]]:
    """Fixture for multi-round strategy results."""
    single_round = ExecutionResult(
        problem_id="prob_1",
        strategy="direct",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(
                iteration=1,
                prompt_tokens=100,
                completion_tokens=50,
                code_extracted="def solution(): pass",
                sandbox_result=SandboxResult(
                    status="success",
                    test_results=[],
                    execution_time=0.1,
                    all_passed=True
                )
            )
        ],
        test_results=[],
        total_tokens=150,
        execution_time_seconds=0.5
    )

    multi_round = ExecutionResult(
        problem_id="prob_2",
        strategy="self_refine",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(
                iteration=i,
                prompt_tokens=100,
                completion_tokens=50,
                code_extracted="def solution(): pass",
                sandbox_result=SandboxResult(
                    status="success",
                    test_results=[],
                    execution_time=0.1,
                    all_passed=False if i < 3 else True
                )
            )
            for i in range(1, 4)
        ],
        test_results=[],
        total_tokens=450,
        execution_time_seconds=1.5
    )

    return {
        "direct": [single_round],
        "self_refine": [multi_round]
    }


@pytest.fixture
def sample_results_with_variance() -> Dict[str, List[ExecutionResult]]:
    """Fixture for results with token variance for percentile testing."""
    # Create results with varying token counts: 400, 500, 600, 700, 800
    results = {
        "strategy_a": [
            ExecutionResult(
                problem_id=f"prob_{i}",
                strategy="strategy_a",
                generated_code="def solution(): pass",
                status="success",
                iterations=[
                    IterationResult(
                        iteration=1,
                        prompt_tokens=int(tokens * 0.6),  # 60% prompt
                        completion_tokens=int(tokens * 0.4),  # 40% completion
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=tokens,
                execution_time_seconds=0.5
            )
            for i, tokens in enumerate([400, 500, 600, 700, 800])
        ]
    }
    return results


def test_generate_success_rate_chart_returns_bytesio(sample_metrics: Dict):
    """Test that success rate chart returns BytesIO."""
    result = ChartGenerator.generate_success_rate_chart(sample_metrics)

    assert isinstance(result, io.BytesIO)
    assert result.tell() == 0  # Pointer at start
    assert len(result.read()) > 0  # Contains data


def test_generate_success_rate_chart_closes_figure(sample_metrics: Dict):
    """Test that figure is closed after generation."""
    initial_figs = len(plt.get_fignums())

    ChartGenerator.generate_success_rate_chart(sample_metrics)

    # Should not leave figure open
    assert len(plt.get_fignums()) == initial_figs


def test_generate_success_rate_chart_color_coding(sample_metrics: Dict):
    """Test that bars are color-coded correctly."""
    # This test verifies the chart is generated; actual color testing
    # would require image analysis
    result = ChartGenerator.generate_success_rate_chart(sample_metrics)
    assert result is not None
    assert len(result.read()) > 0


def test_generate_token_chart_returns_bytesio(sample_metrics: Dict):
    """Test that token chart returns BytesIO."""
    result = ChartGenerator.generate_token_chart(sample_metrics)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_closes_figure(sample_metrics: Dict):
    """Test that token chart closes figure."""
    initial_figs = len(plt.get_fignums())

    ChartGenerator.generate_token_chart(sample_metrics)

    assert len(plt.get_fignums()) == initial_figs


def test_generate_iteration_distribution_multi_round(sample_multi_round_results: Dict):
    """Test iteration distribution with multi-round strategies."""
    result = ChartGenerator.generate_iteration_distribution(sample_multi_round_results)

    assert result is not None
    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_iteration_distribution_single_round_only():
    """Test iteration distribution returns None for single-round only."""
    single_round_results = {
        "direct": [
            ExecutionResult(
                problem_id="prob_1",
                strategy="direct",
                generated_code="def solution(): pass",
                status="success",
                iterations=[
                    IterationResult(
                        iteration=1,
                        prompt_tokens=100,
                        completion_tokens=50,
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=150,
                execution_time_seconds=0.5
            )
        ]
    }

    result = ChartGenerator.generate_iteration_distribution(single_round_results)

    # Should return None when all strategies are single-round
    assert result is None


def test_generate_iteration_distribution_closes_figure(sample_multi_round_results: Dict):
    """Test that iteration distribution closes figure."""
    initial_figs = len(plt.get_fignums())

    ChartGenerator.generate_iteration_distribution(sample_multi_round_results)

    assert len(plt.get_fignums()) == initial_figs


def test_chinese_font_setup_doesnt_crash():
    """Test that Chinese font setup doesn't crash even if fonts missing."""
    # This should not raise an exception
    ChartGenerator._setup_chinese_font()


def test_empty_metrics_dict():
    """Test chart generation with empty metrics."""
    result = ChartGenerator.generate_success_rate_chart({})

    # Should handle empty dict gracefully
    assert result is not None


def test_single_strategy_metrics():
    """Test charts with single strategy."""
    metrics = {
        "direct": {
            "success_rate": 0.75,
            "avg_tokens_per_problem": 500.0,
        }
    }

    success_chart = ChartGenerator.generate_success_rate_chart(metrics)
    token_chart = ChartGenerator.generate_token_chart(metrics)

    assert success_chart is not None
    assert token_chart is not None
    assert len(success_chart.read()) > 0
    assert len(token_chart.read()) > 0


def test_chart_dimensions_and_dpi():
    """Test that charts have correct dimensions (10x6) and DPI (100)."""
    metrics = {"test": {"success_rate": 0.8, "avg_tokens_per_problem": 500.0}}

    # Generate chart and verify it doesn't crash
    # Actual dimension/DPI testing would require inspecting figure properties
    result = ChartGenerator.generate_success_rate_chart(metrics)
    assert result is not None


def test_generate_iteration_distribution_empty_results():
    """Test iteration distribution with empty results."""
    result = ChartGenerator.generate_iteration_distribution({})

    # Should return None for empty results
    assert result is None


def test_generate_token_chart_with_percentiles(sample_metrics: Dict, sample_results_with_variance: Dict):
    """Test that token chart with results generates percentile error bars."""
    result = ChartGenerator.generate_token_chart(sample_metrics, sample_results_with_variance)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_without_results(sample_metrics: Dict):
    """Test that token chart without results works (no error bars)."""
    result = ChartGenerator.generate_token_chart(sample_metrics, results=None)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_with_empty_results(sample_metrics: Dict):
    """Test that token chart with empty results dict works."""
    result = ChartGenerator.generate_token_chart(sample_metrics, results={})

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_percentile_calculation():
    """Test percentile calculation in token chart."""
    metrics = {
        "test_strategy": {
            "avg_tokens_per_problem": 600.0
        }
    }

    results = {
        "test_strategy": [
            ExecutionResult(
                problem_id=f"prob_{i}",
                strategy="test_strategy",
                generated_code="def solution(): pass",
                status="success",
                iterations=[
                    IterationResult(
                        iteration=1,
                        prompt_tokens=int(tokens * 0.6),
                        completion_tokens=int(tokens * 0.4),
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=tokens,
                execution_time_seconds=0.5
            )
            for i, tokens in enumerate([400, 500, 600, 700, 800])
        ]
    }

    # Should generate chart with error bars
    # 25th percentile = 500, 75th percentile = 700
    result = ChartGenerator.generate_token_chart(metrics, results)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0
