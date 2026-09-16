"""
Unit tests for cost estimation functionality in ChartGenerator.
"""

import pytest
from src.reporting.chart_generator import ChartGenerator


class TestCostEstimation:
    """Test cost calculation and dual Y-axis chart generation."""

    def test_calculate_cost_gpt4(self):
        """Test cost calculation for GPT-4."""
        # GPT-4: $30/1M input, $60/1M output
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model='gpt-4'
        )
        expected = (1000 * 30 + 500 * 60) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_gpt35_turbo(self):
        """Test cost calculation for GPT-3.5-turbo."""
        # GPT-3.5-turbo: $0.5/1M input, $1.5/1M output
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=5000,
            completion_tokens=2000,
            model='gpt-3.5-turbo'
        )
        expected = (5000 * 0.5 + 2000 * 1.5) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_claude_sonnet(self):
        """Test cost calculation for Claude 3 Sonnet."""
        # Claude 3 Sonnet: $3/1M input, $15/1M output
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=10000,
            completion_tokens=3000,
            model='claude-3-sonnet'
        )
        expected = (10000 * 3 + 3000 * 15) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_claude_35_sonnet(self):
        """Test cost calculation for Claude 3.5 Sonnet."""
        # Claude 3.5 Sonnet: $3/1M input, $15/1M output
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=8000,
            completion_tokens=2500,
            model='claude-3-5-sonnet'
        )
        expected = (8000 * 3 + 2500 * 15) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_partial_match(self):
        """Test cost calculation with partial model name match."""
        # Should match 'gpt-4' even with specific version
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model='gpt-4-0125-preview'
        )
        expected = (1000 * 30 + 500 * 60) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_default_pricing(self):
        """Test cost calculation with unknown model uses default pricing."""
        # Fixed: Spec requires default pricing of $10/M input, $30/M output
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=2000,
            completion_tokens=1000,
            model='unknown-model-xyz'
        )
        expected = (2000 * 10.0 + 1000 * 30.0) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_no_model(self):
        """Test cost calculation with no model specified uses default."""
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=3000,
            completion_tokens=1500,
            model=None
        )
        expected = (3000 * 10.0 + 1500 * 30.0) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)

    def test_calculate_cost_zero_tokens(self):
        """Test cost calculation with zero tokens."""
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=0,
            completion_tokens=0,
            model='gpt-4'
        )
        assert cost == 0.0

    def test_calculate_cost_case_insensitive(self):
        """Test that model name matching is case-insensitive."""
        cost_upper = ChartGenerator._calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model='GPT-4'
        )
        cost_lower = ChartGenerator._calculate_cost(
            prompt_tokens=1000,
            completion_tokens=500,
            model='gpt-4'
        )
        assert cost_upper == cost_lower

    def test_calculate_cost_large_values(self):
        """Test cost calculation with large token counts."""
        # 1M input + 500K output tokens
        cost = ChartGenerator._calculate_cost(
            prompt_tokens=1_000_000,
            completion_tokens=500_000,
            model='gpt-4'
        )
        expected = (1_000_000 * 30 + 500_000 * 60) / 1_000_000
        assert cost == pytest.approx(expected, rel=1e-6)
        # Should be $60 total
        assert cost == pytest.approx(60.0, rel=1e-6)

    def test_generate_token_chart_with_cost(self):
        """Test that generate_token_chart accepts model parameter."""
        from src.models import ExecutionResult, IterationResult

        # Create mock data
        metrics = {
            'strategy_a': {
                'avg_tokens_per_problem': 1000,
                'success_rate': 0.8
            },
            'strategy_b': {
                'avg_tokens_per_problem': 1500,
                'success_rate': 0.7
            }
        }

        # Create mock results with all required fields
        results = {
            'strategy_a': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def solution(): pass',
                    status='success',
                    iterations=[
                        IterationResult(
                            iteration=1,
                            prompt_tokens=700,
                            completion_tokens=300
                        )
                    ]
                )
            ],
            'strategy_b': [
                ExecutionResult(
                    problem_id='test2',
                    strategy='strategy_b',
                    generated_code='def solution(): pass',
                    status='success',
                    iterations=[
                        IterationResult(
                            iteration=1,
                            prompt_tokens=1000,
                            completion_tokens=500
                        )
                    ]
                )
            ]
        }

        # Should not raise exception
        chart_buf = ChartGenerator.generate_token_chart(
            metrics=metrics,
            results=results,
            model='gpt-4'
        )

        assert chart_buf is not None
        # Buffer is at position 0 after _fig_to_bytes, read to verify content
        content = chart_buf.read()
        assert len(content) > 0

    def test_generate_token_chart_without_model(self):
        """Test that generate_token_chart works without model parameter."""
        metrics = {
            'strategy_a': {'avg_tokens_per_problem': 1000}
        }

        # Should use default pricing and estimate with 70/30 split
        chart_buf = ChartGenerator.generate_token_chart(
            metrics=metrics,
            results=None,
            model=None
        )

        assert chart_buf is not None
        # After generating, the buffer position should be at the end
        # Seek to beginning and check there's content
        chart_buf.seek(0)
        content = chart_buf.read()
        assert len(content) > 0
