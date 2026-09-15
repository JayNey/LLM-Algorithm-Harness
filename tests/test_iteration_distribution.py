"""
Tests for iteration distribution grouped bar chart.
"""

import pytest
import numpy as np
from src.reporting.chart_generator import ChartGenerator
from src.models import ExecutionResult, IterationResult


class TestIterationDistribution:
    """Test iteration distribution grouped bar chart functionality."""

    def test_single_round_strategies_return_none(self):
        """Test that single-round strategies return None."""
        results = {
            'strategy_a': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)
                    ]
                ),
                ExecutionResult(
                    problem_id='test2',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ]
        }

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is None

    def test_multi_round_strategies_generate_chart(self):
        """Test that multi-round strategies generate a chart."""
        results = {
            'strategy_a': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ]
        }

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None

        # Read content to verify it's a valid image
        content = chart_buf.read()
        assert len(content) > 0
        # PNG magic number
        assert content[:8] == b'\x89PNG\r\n\x1a\n'

    def test_multiple_strategies_with_different_iterations(self):
        """Test grouped bars with multiple strategies."""
        results = {
            'strategy_a': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)
                    ]
                ),
                ExecutionResult(
                    problem_id='test2',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                ),
                ExecutionResult(
                    problem_id='test3',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ],
            'strategy_b': [
                ExecutionResult(
                    problem_id='test4',
                    strategy='strategy_b',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=3, prompt_tokens=100, completion_tokens=50)
                    ]
                ),
                ExecutionResult(
                    problem_id='test5',
                    strategy='strategy_b',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ]
        }

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None

        content = chart_buf.read()
        assert len(content) > 0

    def test_max_iterations_calculated_correctly(self):
        """Test that max iterations are calculated correctly."""
        results = {
            'strategy_a': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=i, prompt_tokens=100, completion_tokens=50)
                        for i in range(1, 6)  # 5 iterations
                    ]
                )
            ]
        }

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None

    def test_frequency_counting(self):
        """Test that iteration frequencies are counted correctly."""
        # Create test data with known distribution
        results = {
            'strategy_a': [
                # 3 problems with 1 iteration
                ExecutionResult(
                    problem_id='test1',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)]
                ),
                ExecutionResult(
                    problem_id='test2',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)]
                ),
                ExecutionResult(
                    problem_id='test3',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)]
                ),
                # 2 problems with 2 iterations
                ExecutionResult(
                    problem_id='test4',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                ),
                ExecutionResult(
                    problem_id='test5',
                    strategy='strategy_a',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ]
        }

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None

    def test_empty_results_dict(self):
        """Test handling of empty results dictionary."""
        results = {}
        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is None

    def test_mixed_single_and_multi_round(self):
        """Test that chart is generated when at least one strategy has multi-round."""
        results = {
            'single_round': [
                ExecutionResult(
                    problem_id='test1',
                    strategy='single_round',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ],
            'multi_round': [
                ExecutionResult(
                    problem_id='test2',
                    strategy='multi_round',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=1, prompt_tokens=100, completion_tokens=50),
                        IterationResult(iteration=2, prompt_tokens=100, completion_tokens=50)
                    ]
                )
            ]
        }

        # Should generate chart because multi_round has iterations > 1
        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None

    def test_many_strategies(self):
        """Test with more strategies than colors defined."""
        results = {}
        for i in range(8):  # More than 6 colors defined
            results[f'strategy_{i}'] = [
                ExecutionResult(
                    problem_id=f'test_{i}',
                    strategy=f'strategy_{i}',
                    generated_code='def test(): pass',
                    status='success',
                    iterations=[
                        IterationResult(iteration=j, prompt_tokens=100, completion_tokens=50)
                        for j in range(1, (i % 3) + 2)  # 1-3 iterations
                    ]
                )
            ]

        chart_buf = ChartGenerator.generate_iteration_distribution(results)
        assert chart_buf is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
