"""Tests for evolution analysis integration in experiment reports."""

import json
from pathlib import Path

import pytest

from src.models import CodeQualityMetrics, ExecutionResult, IterationResult


def test_analyze_quality_evolution_with_drops(tmp_path):
    """Test evolution analysis detects drops in experiment results."""
    from src.experiment_report import _analyze_quality_evolution

    # Create mock results with quality drops
    result1 = ExecutionResult(
        problem_id="problem1",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=80.0)),
            IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=60.0)),
        ],
    )

    raw_results = {"combo1": [result1.model_dump()]}

    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    assert analysis["has_evolution_data"] is True
    assert analysis["problems_with_drops"] == 1
    assert analysis["total_drops"] > 0


def test_analyze_quality_evolution_without_quality_data(tmp_path):
    """Test evolution analysis skips results without quality data."""
    from src.experiment_report import _analyze_quality_evolution

    # Create mock results without quality data
    result1 = ExecutionResult(
        problem_id="problem1",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=None),
            IterationResult(iteration=2, code_quality=None),
        ],
    )

    raw_results = {"combo1": [result1.model_dump()]}

    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    assert analysis["has_evolution_data"] is False
    assert analysis["problems_with_drops"] == 0


def test_analyze_quality_evolution_single_iteration(tmp_path):
    """Test evolution analysis skips single-iteration results."""
    from src.experiment_report import _analyze_quality_evolution

    # Create mock results with single iteration
    result1 = ExecutionResult(
        problem_id="problem1",
        strategy="single_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=80.0)),
        ],
    )

    raw_results = {"combo1": [result1.model_dump()]}

    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    assert analysis["has_evolution_data"] is False
    assert analysis["problems_with_drops"] == 0


def test_analyze_quality_evolution_generates_charts(tmp_path):
    """Test evolution analysis generates charts for problems with drops."""
    from src.experiment_report import _analyze_quality_evolution

    # Create mock results with quality drops
    result1 = ExecutionResult(
        problem_id="problem_with_drop",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=85.0)),
            IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=65.0)),
        ],
    )

    raw_results = {"combo1": [result1.model_dump()]}

    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    assert analysis["has_evolution_data"] is True
    assert len(analysis["charts_generated"]) > 0

    # Verify chart file exists
    chart_file = tmp_path / analysis["charts_generated"][0]
    assert chart_file.exists()


def test_analyze_quality_evolution_categorizes_reasons(tmp_path):
    """Test evolution analysis categorizes drop reasons."""
    from src.experiment_report import _analyze_quality_evolution

    # Create mock results with quality drops
    result1 = ExecutionResult(
        problem_id="problem1",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(
                iteration=1,
                code_quality=CodeQualityMetrics(
                    overall_score=80.0,
                    time_complexity={"performance_score": 70.0},
                    readability={"readability_score": 85.0},
                ),
            ),
            IterationResult(
                iteration=2,
                code_quality=CodeQualityMetrics(
                    overall_score=75.0,
                    time_complexity={"performance_score": 90.0},
                    readability={"readability_score": 60.0},
                ),
            ),
        ],
    )

    raw_results = {"combo1": [result1.model_dump()]}

    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    assert analysis["has_evolution_data"] is True
    assert len(analysis["drop_reasons"]) > 0


def test_analyze_quality_evolution_handles_errors_gracefully(tmp_path):
    """Test evolution analysis handles errors without crashing."""
    from src.experiment_report import _analyze_quality_evolution

    # Create invalid results that might cause errors
    raw_results = {
        "combo1": [
            {"problem_id": "invalid", "invalid_field": "data"}
        ]
    }

    # Should not raise exception
    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    # Should return default structure
    assert "has_evolution_data" in analysis
    assert "problems_with_drops" in analysis
    assert "total_drops" in analysis
