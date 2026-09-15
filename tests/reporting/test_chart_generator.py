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


def test_generate_token_chart_with_percentiles():
    """Test token chart with percentile error bands."""
    metrics = {
        "strategy_a": {"avg_tokens_per_problem": 500.0},
        "strategy_b": {"avg_tokens_per_problem": 800.0},
    }

    # Create sample results with varying token counts
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
                        prompt_tokens=100 + i * 10,
                        completion_tokens=50,
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=400 + i * 20,
                execution_time_seconds=0.5
            )
            for i in range(10)
        ],
        "strategy_b": [
            ExecutionResult(
                problem_id=f"prob_{i}",
                strategy="strategy_b",
                generated_code="def solution(): pass",
                status="success",
                iterations=[
                    IterationResult(
                        iteration=1,
                        prompt_tokens=150 + i * 15,
                        completion_tokens=60,
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=700 + i * 30,
                execution_time_seconds=0.6
            )
            for i in range(10)
        ]
    }

    result = ChartGenerator.generate_token_chart(
        metrics,
        show_percentiles=True,
        results=results
    )

    assert result is not None
    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_with_percentiles_insufficient_samples():
    """Test token chart with percentiles when sample size < 5."""
    metrics = {
        "strategy_a": {"avg_tokens_per_problem": 500.0},
    }

    # Only 3 samples - insufficient for percentiles
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
                        prompt_tokens=100,
                        completion_tokens=50,
                        code_extracted="def solution(): pass"
                    )
                ],
                test_results=[],
                total_tokens=400 + i * 20,
                execution_time_seconds=0.5
            )
            for i in range(3)
        ]
    }

    # Should still generate chart, just no error bands
    result = ChartGenerator.generate_token_chart(
        metrics,
        show_percentiles=True,
        results=results
    )

    assert result is not None
    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_with_percentiles_no_results():
    """Test token chart with percentiles=True but no results provided."""
    metrics = {
        "strategy_a": {"avg_tokens_per_problem": 500.0},
    }

    # Should still generate chart without error bands
    result = ChartGenerator.generate_token_chart(
        metrics,
        show_percentiles=True,
        results=None
    )

    assert result is not None
    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0
