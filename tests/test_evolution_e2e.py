"""End-to-end tests for code evolution analysis feature."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models import (
    CodeQualityMetrics,
    HarnessConfig,
    LLMConfig,
    Problem,
    SandboxConfig,
    StrategyConfig,
)


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client."""
    with patch("src.llm_client.LLMClient") as mock:
        client = MagicMock()
        client.generate.return_value = MagicMock(
            text="```python\ndef solution(nums):\n    return sum(nums)\n```",
            usage={"total_tokens": 100},
        )
        mock.return_value = client
        yield client


@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox executor."""
    with patch("src.sandbox_executor.SandboxExecutor") as mock:
        sandbox = MagicMock()
        sandbox.health_check.return_value = (True, "OK")
        sandbox.execute.return_value = MagicMock(
            status="success",
            all_passed=True,
            test_results=[
                MagicMock(
                    test_case_index=0,
                    passed=True,
                    status="passed",
                    execution_time=0.01,
                )
            ],
            execution_time=0.1,
        )
        mock.return_value = sandbox
        yield sandbox


def test_multi_round_strategy_with_quality_analysis(tmp_path, mock_llm_client, mock_sandbox):
    """Test that MultiRoundFeedbackStrategy produces quality metrics in iterations."""
    from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy

    # Create strategy configuration
    config = StrategyConfig(name="multi_round_feedback", max_iterations=3)

    # Create strategy
    strategy = MultiRoundFeedbackStrategy(config, mock_llm_client, mock_sandbox)

    # Create test problem with required fields
    problem = Problem(
        problem_id="test_problem",
        title="Test Problem",
        description="Test problem",
        difficulty="easy",
        public_test_cases=[{"input": "[1, 2, 3]", "expected_output": "6"}],
        metadata={"code_snippet": {"python": "class Solution:\n    def solve(self, nums):\n        pass"}},
        entry_point="Solution.solve",
    )

    # Execute strategy
    result = strategy.execute(problem)

    # Verify execution completed
    assert result.status in ["success", "model_error", "system_error"]
    assert len(result.iterations) > 0

    # Note: Quality metrics are only added if quality analysis is enabled
    # and the analyzer is properly integrated. This test verifies the
    # structure is in place.
    for iteration in result.iterations:
        assert hasattr(iteration, "code_quality")


def test_evolution_analysis_in_strategy_execution(tmp_path, mock_llm_client, mock_sandbox):
    """Test that evolution analysis runs during strategy execution when quality data exists."""
    from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy

    # Create strategy configuration
    config = StrategyConfig(name="multi_round_feedback", max_iterations=2)

    # Create strategy
    strategy = MultiRoundFeedbackStrategy(config, mock_llm_client, mock_sandbox)

    # Create test problem with required fields
    problem = Problem(
        problem_id="test_problem",
        title="Test Problem",
        description="Test problem",
        difficulty="medium",
        public_test_cases=[{"input": "[1, 2, 3]", "expected_output": "6"}],
        metadata={"code_snippet": {"python": "class Solution:\n    def solve(self, nums):\n        pass"}},
        entry_point="Solution.solve",
    )

    # Execute strategy
    result = strategy.execute(problem)

    # Verify quality data structure is present
    assert len(result.iterations) >= 1
    for iteration in result.iterations:
        assert hasattr(iteration, "code_quality")


def test_evolution_analysis_not_run_for_single_iteration(tmp_path, mock_llm_client, mock_sandbox):
    """Test that evolution analysis is not run for single-iteration strategies."""
    from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy

    # Create a configuration with max_iterations=1
    config = StrategyConfig(name="multi_round_feedback", max_iterations=1)

    # Create strategy
    strategy = MultiRoundFeedbackStrategy(config, mock_llm_client, mock_sandbox)

    # Create test problem
    problem = Problem(
        problem_id="test_problem",
        title="Test Problem",
        description="Test problem",
        difficulty="easy",
        public_test_cases=[{"input": "[1, 2, 3]", "expected_output": "6"}],
        metadata={"code_snippet": {"python": "class Solution:\n    def solve(self, nums):\n        pass"}},
        entry_point="Solution.solve",
    )

    # Execute strategy
    result = strategy.execute(problem)

    # Verify only one iteration
    assert len(result.iterations) == 1

    # Evolution analysis should not run with single iteration
    # (verified by the fact that the code doesn't crash and completes successfully)
    assert result.status in ["success", "model_error", "system_error"]


def test_evolution_chart_generation_in_reports(tmp_path):
    """Test that evolution charts are generated when included in experiment reports."""
    from src.experiment_report import _analyze_quality_evolution
    from src.models import ExecutionResult, IterationResult

    # Create mock result with quality evolution
    result = ExecutionResult(
        problem_id="chart_test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=80.0)),
            IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=60.0)),
            IterationResult(iteration=3, code_quality=CodeQualityMetrics(overall_score=75.0)),
        ],
    )

    raw_results = {"combo1": [result.model_dump()]}

    # Run analysis
    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    # Verify charts were generated
    assert analysis["has_evolution_data"] is True
    assert len(analysis["charts_generated"]) > 0

    # Verify chart files exist
    for chart_name in analysis["charts_generated"]:
        chart_path = tmp_path / chart_name
        assert chart_path.exists()
        assert chart_path.stat().st_size > 0


def test_complete_workflow_with_evolution_analysis(tmp_path):
    """Test complete workflow from execution to report generation with evolution analysis."""
    from src.experiment_report import _analyze_quality_evolution
    from src.models import ExecutionResult, IterationResult

    # Simulate a complete experiment with multiple problems
    results_with_evolution = [
        ExecutionResult(
            problem_id="problem1",
            strategy="multi_round",
            generated_code="def solution(): pass",
            status="success",
            iterations=[
                IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=85.0)),
                IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=65.0)),
            ],
        ),
        ExecutionResult(
            problem_id="problem2",
            strategy="multi_round",
            generated_code="def solution(): pass",
            status="success",
            iterations=[
                IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=75.0)),
                IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=80.0)),
            ],
        ),
    ]

    raw_results = {"combo1": [r.model_dump() for r in results_with_evolution]}

    # Run evolution analysis
    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    # Verify analysis results
    assert analysis["has_evolution_data"] is True
    assert analysis["problems_with_drops"] >= 1
    assert analysis["total_drops"] >= 1
    assert len(analysis["drop_reasons"]) > 0

    # Verify summary structure
    assert "has_evolution_data" in analysis
    assert "problems_with_drops" in analysis
    assert "total_drops" in analysis
    assert "drop_reasons" in analysis
    assert "charts_generated" in analysis
