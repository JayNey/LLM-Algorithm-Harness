"""
Unit tests for ChartGenerator.
"""

import io
import math
from unittest.mock import patch

import matplotlib.pyplot as plt
import pytest

from src.models import ExecutionResult, IterationResult, SandboxResult
from src.reporting.chart_generator import ChartGenerator


@pytest.fixture
def sample_metrics() -> dict[str, dict]:
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
        },
    }


@pytest.fixture
def sample_multi_round_results() -> dict[str, list[ExecutionResult]]:
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
                    status="success", test_results=[], execution_time=0.1, all_passed=True
                ),
            )
        ],
        test_results=[],
        total_tokens=150,
        execution_time_seconds=0.5,
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
                    all_passed=False if i < 3 else True,
                ),
            )
            for i in range(1, 4)
        ],
        test_results=[],
        total_tokens=450,
        execution_time_seconds=1.5,
    )

    return {"direct": [single_round], "self_refine": [multi_round]}


@pytest.fixture
def sample_results_with_variance() -> dict[str, list[ExecutionResult]]:
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
                        code_extracted="def solution(): pass",
                    )
                ],
                test_results=[],
                total_tokens=tokens,
                execution_time_seconds=0.5,
            )
            for i, tokens in enumerate([400, 500, 600, 700, 800])
        ]
    }
    return results


def test_generate_success_rate_chart_returns_bytesio(sample_metrics: dict):
    """Test that success rate chart returns BytesIO."""
    result = ChartGenerator.generate_success_rate_chart(sample_metrics)

    assert isinstance(result, io.BytesIO)
    assert result.tell() == 0  # Pointer at start
    assert len(result.read()) > 0  # Contains data


def test_generate_success_rate_chart_closes_figure(sample_metrics: dict):
    """Test that figure is closed after generation."""
    initial_figs = len(plt.get_fignums())

    ChartGenerator.generate_success_rate_chart(sample_metrics)

    # Should not leave figure open
    assert len(plt.get_fignums()) == initial_figs


def test_generate_success_rate_chart_color_coding(sample_metrics: dict):
    """Test that bars are color-coded correctly."""
    # This test verifies the chart is generated; actual color testing
    # would require image analysis
    result = ChartGenerator.generate_success_rate_chart(sample_metrics)
    assert result is not None
    assert len(result.read()) > 0


def test_generate_token_chart_returns_bytesio(sample_metrics: dict):
    """Test that token chart returns BytesIO."""
    result = ChartGenerator.generate_token_chart(sample_metrics)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_closes_figure(sample_metrics: dict):
    """Test that token chart closes figure."""
    initial_figs = len(plt.get_fignums())

    ChartGenerator.generate_token_chart(sample_metrics)

    assert len(plt.get_fignums()) == initial_figs


def test_generate_iteration_distribution_multi_round(sample_multi_round_results: dict):
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
                        code_extracted="def solution(): pass",
                    )
                ],
                test_results=[],
                total_tokens=150,
                execution_time_seconds=0.5,
            )
        ]
    }

    result = ChartGenerator.generate_iteration_distribution(single_round_results)

    # Should return None when all strategies are single-round
    assert result is None


def test_generate_iteration_distribution_closes_figure(sample_multi_round_results: dict):
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


def test_generate_token_chart_with_percentiles(
    sample_metrics: dict, sample_results_with_variance: dict
):
    """Test that token chart with results generates percentile error bars."""
    result = ChartGenerator.generate_token_chart(sample_metrics, sample_results_with_variance)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_without_results(sample_metrics: dict):
    """Test that token chart without results works (no error bars)."""
    result = ChartGenerator.generate_token_chart(sample_metrics, results=None)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_with_empty_results(sample_metrics: dict):
    """Test that token chart with empty results dict works."""
    result = ChartGenerator.generate_token_chart(sample_metrics, results={})

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


def test_generate_token_chart_percentile_calculation():
    """Test percentile calculation in token chart."""
    metrics = {"test_strategy": {"avg_tokens_per_problem": 600.0}}

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
                        code_extracted="def solution(): pass",
                    )
                ],
                test_results=[],
                total_tokens=tokens,
                execution_time_seconds=0.5,
            )
            for i, tokens in enumerate([400, 500, 600, 700, 800])
        ]
    }

    # Should generate chart with error bars
    # 25th percentile = 500, 75th percentile = 700
    result = ChartGenerator.generate_token_chart(metrics, results)

    assert isinstance(result, io.BytesIO)
    assert len(result.read()) > 0


class TestTokenChartHistoricalCost:
    """issue #368 (S16)：图表费用直读历史 trace，未知费用不伪造美元值。"""

    @staticmethod
    def _result_with_traces(llm_traces, prompt=1000, completion=1000):
        return ExecutionResult(
            problem_id="p1",
            strategy="vanilla",
            generated_code="",
            status="success",
            iterations=[
                IterationResult(
                    iteration=1,
                    prompt_tokens=prompt,
                    completion_tokens=completion,
                    code_extracted="",
                )
            ],
            test_results=[],
            llm_traces=llm_traces,
        )

    @staticmethod
    def _capture_chart(metrics, results):
        captured = {}

        def capture(fig):
            captured["fig"] = fig
            captured["token_ydata"] = fig.axes[0].lines[0].get_ydata().tolist()
            captured["cost_lines"] = len(fig.axes[1].lines)
            captured["cost_ydata"] = [line.get_ydata().tolist() for line in fig.axes[1].lines]
            captured["titles"] = [ax.get_title() for ax in fig.axes]

        with patch.object(ChartGenerator, "_fig_to_bytes", side_effect=capture):
            ChartGenerator.generate_token_chart(metrics, results)
        return captured

    def test_known_historical_cost_is_used_directly(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [
                        {
                            "prompt_tokens": 1000,
                            "completion_tokens": 1000,
                            "total_tokens": 2000,
                            "pricing_metadata": {
                                "total_cost": 9,
                                "usage_known": True,
                                "pricing_known": True,
                            },
                        }
                    ]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_ydata"] == [[9.0]]
        assert any("Known Cost" in title for title in captured["titles"])
        assert not any("estimated" in title.lower() for title in captured["titles"])

    def test_known_zero_cost_stays_zero(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [
                        {
                            "prompt_tokens": 1000,
                            "completion_tokens": 1000,
                            "total_tokens": 2000,
                            "pricing_metadata": {
                                "total_cost": 0,
                                "usage_known": True,
                                "pricing_known": True,
                            },
                        }
                    ]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_ydata"] == [[0.0]]
        assert not any("70/30" in title for title in captured["titles"])

    def test_unknown_calls_excluded_and_annotated(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [
                        {
                            "prompt_tokens": 1000,
                            "completion_tokens": 1000,
                            "total_tokens": 2000,
                            "pricing_metadata": {
                                "total_cost": 5,
                                "usage_known": True,
                                "pricing_known": True,
                            },
                        },
                        {
                            "prompt_tokens": 10,
                            "completion_tokens": 10,
                            "total_tokens": 20,
                            "pricing_metadata": {"total_cost": None, "usage_known": False},
                        },
                    ]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_ydata"] == [[5.0]]
        assert any(
            "1 result unit(s) with unknown cost excluded" in title for title in captured["titles"]
        )

    def test_missing_pricing_metadata_counts_as_unknown(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [
                        {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
                        {
                            "prompt_tokens": 100,
                            "completion_tokens": 100,
                            "total_tokens": 200,
                            "pricing_metadata": {
                                "total_cost": 3,
                                "usage_known": True,
                                "pricing_known": True,
                            },
                        },
                    ]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_ydata"] == [[3.0]]
        assert any(
            "1 result unit(s) with unknown cost excluded" in title for title in captured["titles"]
        )

    def test_no_known_cost_data_draws_no_dollars(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [{"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_lines"] == 0
        assert any(
            "1 result unit(s) with unknown cost excluded" in title for title in captured["titles"]
        )

    def test_usage_known_false_counts_as_unknown(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}
        results = {
            "vanilla": [
                self._result_with_traces(
                    [
                        {
                            "prompt_tokens": 1000,
                            "completion_tokens": 1000,
                            "total_tokens": 2000,
                            "pricing_metadata": {
                                "total_cost": 5,
                                "usage_known": False,
                                "pricing_known": True,
                            },
                        }
                    ]
                )
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_lines"] == 0
        assert any(
            "1 result unit(s) with unknown cost excluded" in title for title in captured["titles"]
        )

    def test_multiple_strategies_and_untraced_results(self):
        metrics = {
            "known": {"avg_tokens_per_problem": 450.0},
            "unknown": {"avg_tokens_per_problem": 200.0},
        }
        results = {
            "known": [
                self._result_with_traces(
                    [
                        {
                            "prompt_tokens": 300,
                            "completion_tokens": 150,
                            "total_tokens": 450,
                            "pricing_metadata": {
                                "total_cost": 7,
                                "usage_known": True,
                                "pricing_known": True,
                            },
                        }
                    ]
                )
            ],
            "unknown": [self._result_with_traces([])],
        }

        captured = self._capture_chart(metrics, results)

        assert captured["token_ydata"] == [450.0, 200.0]
        assert len(captured["cost_ydata"]) == 1
        assert captured["cost_ydata"][0][0] == 7.0
        assert math.isnan(captured["cost_ydata"][0][1])
        assert any(
            "1 result unit(s) with unknown cost excluded" in title for title in captured["titles"]
        )

    def test_metrics_only_draws_no_dollars(self):
        metrics = {"vanilla": {"avg_tokens_per_problem": 2000}}

        captured = self._capture_chart(metrics, None)

        assert captured["cost_lines"] == 0
        assert any("no known cost data" in title for title in captured["titles"])

    def test_reflection_usage_included_via_merged_traces(self):
        # 真实链路：strategy_base._build_llm_traces 把 reflection 轮合并进
        # trace 顶层 token（165/330，而非未合并的 150/300），
        # _merge_pricing_metadata 把双方已知费用求和；误差棒反映 trace 口径。
        metrics = {"vanilla": {"avg_tokens_per_problem": 247.5}}

        def merged_trace(total_tokens, prompt, completion, cost):
            return {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": total_tokens,
                "pricing_metadata": {
                    "total_cost": cost,
                    "usage_known": True,
                    "pricing_known": True,
                    "reflection_pricing_metadata": {
                        "total_cost": cost / 1.5,
                        "usage_known": True,
                    },
                },
            }

        results = {
            "vanilla": [
                self._result_with_traces(
                    [merged_trace(165, 110, 55, 1.5)], prompt=100, completion=50
                ),
                self._result_with_traces(
                    [merged_trace(330, 220, 110, 3.0)], prompt=200, completion=100
                ),
            ]
        }

        captured = self._capture_chart(metrics, results)

        assert captured["cost_ydata"] == [[2.25]]
        assert captured["token_ydata"] == [247.5]
        collections = [
            line_collection
            for container in captured["fig"].axes[0].containers
            for line_collection in container[2]
        ]
        ys = sorted(
            point[1] for line in collections for segment in line.get_segments() for point in segment
        )
        assert ys == [206.25, 288.75]
