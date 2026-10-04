"""Tests for evolution report generation."""

from src.models import CodeQualityMetrics, ExecutionResult, IterationResult
from src.reporting.evolution_report import (
    generate_evolution_section,
    should_include_evolution_analysis,
)


def test_should_include_evolution_analysis_with_quality_data():
    """Test that evolution analysis is included when quality data is present."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    assert should_include_evolution_analysis(result) is True


def test_should_include_evolution_analysis_without_quality_data():
    """Test that evolution analysis is skipped when no quality data is present."""
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

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    assert should_include_evolution_analysis(result) is False


def test_should_include_evolution_analysis_single_iteration():
    """Test that evolution analysis is skipped for single iteration."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    assert should_include_evolution_analysis(result) is False


def test_generate_evolution_section_with_quality_data():
    """Test evolution section generation with quality data."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    section = generate_evolution_section(result)

    # Check that section contains expected content
    assert "## Code Quality Evolution Analysis" in section
    assert "### Summary" in section
    assert "Total iterations: 2" in section


def test_generate_evolution_section_without_quality_data():
    """Test that empty section is returned when no quality data."""
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

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    section = generate_evolution_section(result)

    assert section == ""


def test_generate_evolution_section_with_chart(tmp_path):
    """Test evolution section generation with chart output."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test_problem",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    section = generate_evolution_section(result, output_dir=tmp_path)

    # Check that section contains chart reference
    assert "## Code Quality Evolution Analysis" in section
    assert "演化趋势图表" in section
    assert "test_problem_evolution.png" in section

    # Verify chart file was created
    chart_path = tmp_path / "test_problem_evolution.png"
    assert chart_path.exists()


def test_generate_evolution_section_single_iteration():
    """Test that empty section is returned for single iteration."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    section = generate_evolution_section(result)

    assert section == ""
