"""Tests for quality analysis integration in MultiRoundFeedbackStrategy."""

import pytest

from src.models import CodeQualityMetrics, ExecutionResult, IterationResult


def test_quality_analysis_detects_drops():
    """Test that quality drops are detected when present in execution result."""
    from src.analysis.evolution import EvolutionAnalyzer

    # Create an execution result with quality drops
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=85.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=60.0),  # Significant drop
        ),
    ]

    execution_result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    # Verify quality analysis detects the drop
    analyzer = EvolutionAnalyzer(execution_result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) > 0
    assert any(drop.metric_name == "overall_score" for drop in drops)


def test_quality_analysis_no_drops_when_improving():
    """Test that no drops are detected when quality improves."""
    from src.analysis.evolution import EvolutionAnalyzer

    # Create an execution result with improving quality
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=75.0),  # Improvement
        ),
    ]

    execution_result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    # Verify no quality drops are detected
    analyzer = EvolutionAnalyzer(execution_result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 0


def test_quality_analysis_skipped_for_single_iteration():
    """Test that quality analysis is skipped for single-iteration executions."""
    from src.analysis.evolution import EvolutionAnalyzer

    # Create an execution result with only one iteration
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=85.0),
        ),
    ]

    execution_result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    # Verify no drops detected (need at least 2 iterations for comparison)
    analyzer = EvolutionAnalyzer(execution_result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 0


def test_quality_analysis_handles_missing_quality_data():
    """Test that quality analysis handles iterations without quality data."""
    from src.analysis.evolution import EvolutionAnalyzer

    # Create an execution result with missing quality data
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=None,  # Missing quality data
        ),
        IterationResult(
            iteration=3,
            code_quality=CodeQualityMetrics(overall_score=60.0),
        ),
    ]

    execution_result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    # Verify analysis doesn't crash and handles missing data gracefully
    analyzer = EvolutionAnalyzer(execution_result)
    drops = analyzer.identify_quality_drops()

    # Should be a list (possibly empty, depending on implementation)
    assert isinstance(drops, list)


def test_quality_analysis_not_performed_without_quality_data():
    """Test that quality analysis is skipped when no quality data is present."""
    from src.analysis.evolution import EvolutionAnalyzer

    # Create an execution result with no quality data
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=None,
        ),
        IterationResult(
            iteration=2,
            code_quality=None,
        ),
    ]

    execution_result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    # Verify no drops detected when there's no quality data
    analyzer = EvolutionAnalyzer(execution_result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 0


