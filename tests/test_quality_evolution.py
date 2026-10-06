"""Tests for the quality evolution analysis aggregation."""

from unittest.mock import patch

import pytest

from src.code_quality.models import CodeQualityMetrics, ReadabilityScore
from src.experiment_report import _analyze_quality_evolution
from src.models import ExecutionResult, IterationResult


def _quality_iterations():
    return [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(readability_score=80.0), overall_score=80.0
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(readability_score=40.0), overall_score=40.0
            ),
        ),
    ]


def _raw_result_dict():
    return {
        "problem_id": "p1",
        "strategy": "multi_round",
        "generated_code": "print(1)",
        "status": "success",
        "iterations": [item.model_dump(mode="json") for item in _quality_iterations()],
    }


class TestAnalyzeQualityEvolution:
    def test_counts_drops_and_generates_chart(self, tmp_path):
        summary = _analyze_quality_evolution(
            {"multi_round__r1": [_raw_result_dict()]}, tmp_path
        )
        assert summary["has_evolution_data"] is True
        assert summary["problems_with_drops"] == 1
        assert summary["total_drops"] >= 1
        assert summary["charts_generated"] == ["evolution_p1.png"]
        assert any(
            "syntax" in reason or "Readability" in reason
            for reason in summary["drop_reasons"]
        )

    def test_chart_failure_is_optional(self, tmp_path):
        with patch(
            "src.analysis.evolution.EvolutionAnalyzer.generate_evolution_chart",
            side_effect=RuntimeError("chart down"),
        ):
            summary = _analyze_quality_evolution(
                {"multi_round__r1": [_raw_result_dict()]}, tmp_path
            )
        assert summary["has_evolution_data"] is True
        assert summary["charts_generated"] == []

    def test_single_iteration_results_are_skipped(self, tmp_path):
        raw = {
            "multi_round__r1": [
                {
                    "problem_id": "p1",
                    "strategy": "multi_round",
                    "generated_code": "",
                    "status": "success",
                    "iterations": [_quality_iterations()[0].model_dump(mode="json")],
                }
            ]
        }
        summary = _analyze_quality_evolution(raw, tmp_path)
        assert summary["has_evolution_data"] is False

    def test_invalid_result_records_are_skipped(self, tmp_path):
        raw = {
            "multi_round__r1": [
                {"status": "not-a-real-record"},
                _raw_result_dict(),
            ]
        }
        summary = _analyze_quality_evolution(raw, tmp_path)
        assert summary["has_evolution_data"] is True

    def test_import_error_disables_analysis(self, tmp_path):
        import sys

        with patch.dict(sys.modules, {"src.analysis.evolution": None}):
            summary = _analyze_quality_evolution(
                {"multi_round__r1": [_raw_result_dict()]}, tmp_path
            )
        assert summary["has_evolution_data"] is False

    def test_unexpected_shape_is_contained(self, tmp_path):
        summary = _analyze_quality_evolution(None, tmp_path)
        assert summary["has_evolution_data"] is False


def test_space_complexity_drop_detected():
    from src.analysis.evolution import EvolutionAnalyzer
    from src.code_quality.models import SpaceComplexityScore
    from src.models import ExecutionResult, IterationResult

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                space_complexity=SpaceComplexityScore(memory_efficiency_score=90.0),
                overall_score=90.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                space_complexity=SpaceComplexityScore(memory_efficiency_score=50.0),
                overall_score=50.0,
            ),
        ),
    ]
    result = ExecutionResult(
        problem_id="p1",
        strategy="multi_round",
        generated_code="",
        status="success",
        iterations=iterations,
    )
    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()
    assert any(drop.metric_name == "space_complexity" for drop in drops)


def test_chart_skips_iterations_without_quality_data(tmp_path):
    from src.analysis.evolution import EvolutionAnalyzer
    from src.models import ExecutionResult, IterationResult

    iterations = [
        IterationResult(iteration=1),
        IterationResult(iteration=2),
    ]
    result = ExecutionResult(
        problem_id="p1",
        strategy="multi_round",
        generated_code="",
        status="success",
        iterations=iterations,
    )
    with pytest.raises(ValueError, match="at least 2 iterations with quality data"):
        EvolutionAnalyzer(result).generate_evolution_chart(tmp_path / "evolution.png")
    assert not (tmp_path / "evolution.png").exists()


def test_chart_renders_with_mixed_quality_scores(tmp_path):
    from src.analysis.evolution import EvolutionAnalyzer
    from src.code_quality.models import SpaceComplexityScore
    from src.models import ExecutionResult, IterationResult

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(readability_score=80.0), overall_score=80.0
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(readability_score=60.0),
                space_complexity=SpaceComplexityScore(memory_efficiency_score=70.0),
                overall_score=60.0,
            ),
        ),
    ]
    result = ExecutionResult(
        problem_id="p1",
        strategy="multi_round",
        generated_code="",
        status="success",
        iterations=iterations,
    )
    out = tmp_path / "evolution.png"
    EvolutionAnalyzer(result).generate_evolution_chart(out)
    assert out.exists() and out.stat().st_size > 0
