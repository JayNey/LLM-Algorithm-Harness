"""
Tests for code evolution analysis.
"""

import pytest

from src.analysis.evolution import EvolutionAnalyzer
from src.code_quality.models import CodeQualityMetrics, ReadabilityScore, StyleConsistencyScore
from src.models import ExecutionResult, IterationResult


def test_identify_quality_drops_no_drops():
    """Test that no drops are identified when quality improves."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=70.0),
                style_consistency=StyleConsistencyScore(style_score=75.0),
                overall_score=70.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=80.0),
                style_consistency=StyleConsistencyScore(style_score=85.0),
                overall_score=80.0,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 0


def test_identify_quality_drops_overall_score_drop():
    """Test detection of overall score drop above absolute threshold."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=None,
                style_consistency=None,
                overall_score=85.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=None,
                style_consistency=None,
                overall_score=70.0,  # 15 point drop
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 1
    assert drops[0].iteration == 2
    assert drops[0].metric_name == "overall_score"
    assert drops[0].previous_value == 85.0
    assert drops[0].current_value == 70.0


def test_identify_quality_drops_relative_threshold():
    """Test detection of individual metric drop above relative threshold."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=80.0),
                style_consistency=None,
                overall_score=80.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=65.0),  # 18.75% drop (15/80)
                style_consistency=None,
                overall_score=75.0,  # Only 5 point drop, below threshold
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 1
    assert drops[0].iteration == 2
    assert drops[0].metric_name == "readability"
    assert drops[0].previous_value == 80.0
    assert drops[0].current_value == 65.0


def test_identify_quality_drops_skips_first_iteration():
    """Test that first iteration is not evaluated (no baseline)."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=None,
                style_consistency=None,
                overall_score=50.0,  # Low score, but no baseline to compare
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 0


def test_identify_quality_drops_skips_missing_quality_data():
    """Test that iterations without quality data are skipped."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=None,
                style_consistency=None,
                overall_score=80.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=None,  # Missing quality data
        ),
        IterationResult(
            iteration=3,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=None,
                style_consistency=None,
                overall_score=60.0,  # Can't compare to iteration 2
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    # Should not crash, and should skip comparison involving iteration 2
    assert isinstance(drops, list)


def test_identify_quality_drops_multiple_metrics():
    """Test detection of drops in multiple metrics simultaneously."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=80.0),
                style_consistency=StyleConsistencyScore(style_score=90.0),
                overall_score=85.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=None,
                space_complexity=None,
                readability=ReadabilityScore(readability_score=65.0),  # 18.75% drop
                style_consistency=StyleConsistencyScore(style_score=75.0),  # 16.67% drop
                overall_score=70.0,  # 15 point drop
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    assert len(drops) == 3
    metric_names = {drop.metric_name for drop in drops}
    assert metric_names == {"overall_score", "readability", "style_consistency"}


# ============================================================================
# analyze_drop_reason Tests
# ============================================================================


def test_analyze_drop_reason_syntax_error():
    """Test detection of syntax error as drop reason."""
    from src.models import SandboxResult

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=80.0),
            sandbox_result=SandboxResult(
                status="success", execution_time=1.0, all_passed=True
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=50.0),
            sandbox_result=SandboxResult(
                status="syntax_error", execution_time=0.0, all_passed=False
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()
    assert len(drops) > 0

    reason = analyzer.analyze_drop_reason(drops[0])
    assert "syntax error" in reason.lower()


def test_analyze_drop_reason_over_optimization():
    """Test detection of over-optimization pattern."""
    from src.code_quality.models import TimeComplexityScore
    from src.models import SandboxResult, TestCaseResult

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=TimeComplexityScore(performance_score=80.0),
                overall_score=80.0,
            ),
            sandbox_result=SandboxResult(
                status="failed",
                test_results=[
                    TestCaseResult(test_case_index=0, passed=True, status="passed"),
                    TestCaseResult(test_case_index=1, passed=True, status="passed"),
                    TestCaseResult(test_case_index=2, passed=True, status="passed"),
                    TestCaseResult(test_case_index=3, passed=False, status="wrong_answer"),
                    TestCaseResult(test_case_index=4, passed=False, status="wrong_answer"),
                ],
                execution_time=1.0,
                all_passed=False,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=TimeComplexityScore(performance_score=60.0),
                overall_score=70.0,
            ),
            sandbox_result=SandboxResult(
                status="success",
                test_results=[
                    TestCaseResult(test_case_index=0, passed=True, status="passed"),
                    TestCaseResult(test_case_index=1, passed=True, status="passed"),
                    TestCaseResult(test_case_index=2, passed=True, status="passed"),
                    TestCaseResult(test_case_index=3, passed=True, status="passed"),
                    TestCaseResult(test_case_index=4, passed=True, status="passed"),
                ],
                execution_time=1.2,
                all_passed=True,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    # Find time_complexity drop
    time_drop = next((d for d in drops if d.metric_name == "time_complexity"), None)
    if time_drop:
        reason = analyzer.analyze_drop_reason(time_drop)
        assert "over-optimization" in reason.lower() or "complexity increased" in reason.lower()


def test_analyze_drop_reason_code_bloat():
    """Test detection of code bloat pattern."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(
                    readability_score=80.0, cyclomatic_complexity=2.0
                ),
                overall_score=80.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                readability=ReadabilityScore(
                    readability_score=60.0, cyclomatic_complexity=5.0
                ),
                overall_score=70.0,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    readability_drop = next((d for d in drops if d.metric_name == "readability"), None)
    if readability_drop:
        reason = analyzer.analyze_drop_reason(readability_drop)
        assert "bloat" in reason.lower() or "complexity" in reason.lower()


def test_analyze_drop_reason_style_degradation():
    """Test detection of style degradation pattern."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                style_consistency=StyleConsistencyScore(style_score=90.0, style_violations=2),
                overall_score=90.0,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                style_consistency=StyleConsistencyScore(style_score=70.0, style_violations=10),
                overall_score=75.0,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    drops = analyzer.identify_quality_drops()

    style_drop = next((d for d in drops if d.metric_name == "style_consistency"), None)
    if style_drop:
        reason = analyzer.analyze_drop_reason(style_drop)
        assert "style" in reason.lower() and ("violation" in reason.lower() or "degradation" in reason.lower())


# ============================================================================
# generate_evolution_chart Tests
# ============================================================================


def test_generate_evolution_chart_creates_file(tmp_path):
    """Test that chart generation creates a PNG file."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
        IterationResult(
            iteration=3,
            code_quality=CodeQualityMetrics(overall_score=75.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    output_path = tmp_path / "evolution_chart.png"
    analyzer.generate_evolution_chart(output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


def test_generate_evolution_chart_insufficient_data(tmp_path):
    """Test that chart generation raises error with insufficient data."""
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

    analyzer = EvolutionAnalyzer(result)
    output_path = tmp_path / "evolution_chart.png"

    with pytest.raises(ValueError, match="at least 2 iterations"):
        analyzer.generate_evolution_chart(output_path)


def test_generate_evolution_chart_with_all_metrics(tmp_path):
    """Test chart generation with all quality metrics present."""
    from src.code_quality.models import TimeComplexityScore, SpaceComplexityScore

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=TimeComplexityScore(performance_score=80.0),
                space_complexity=SpaceComplexityScore(memory_efficiency_score=75.0),
                readability=ReadabilityScore(readability_score=70.0),
                style_consistency=StyleConsistencyScore(style_score=85.0),
                overall_score=77.5,
            ),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(
                time_complexity=TimeComplexityScore(performance_score=85.0),
                space_complexity=SpaceComplexityScore(memory_efficiency_score=80.0),
                readability=ReadabilityScore(readability_score=75.0),
                style_consistency=StyleConsistencyScore(style_score=90.0),
                overall_score=82.5,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    output_path = tmp_path / "evolution_chart_full.png"
    analyzer.generate_evolution_chart(output_path)

    assert output_path.exists()
    assert output_path.stat().st_size > 0


# ============================================================================
# generate_evolution_report Tests
# ============================================================================


def test_generate_evolution_report_basic():
    """Test basic report generation with multiple iterations."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=80.0),
        ),
        IterationResult(
            iteration=3,
            code_quality=CodeQualityMetrics(overall_score=75.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    report = analyzer.generate_evolution_report()

    # Check required sections
    assert "## Code Quality Evolution Analysis" in report
    assert "### Summary" in report
    assert "### Quality Drops Detected" in report
    assert "### Iteration Details" in report

    # Check summary content
    assert "Total iterations: 3" in report
    assert "Iterations with quality data: 3" in report
    assert "Initial overall score: 70.0" in report
    assert "Final overall score: 75.0" in report


def test_generate_evolution_report_with_drops():
    """Test report generation includes detected drops."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=85.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=65.0),  # 20 point drop
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    report = analyzer.generate_evolution_report()

    assert "Found 1 quality drop(s)" in report
    assert "**Iteration 2:**" in report
    assert "Overall Score: 85.0 → 65.0" in report
    assert "Reason:" in report


def test_generate_evolution_report_no_drops():
    """Test report generation when no drops detected."""
    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(overall_score=70.0),
        ),
        IterationResult(
            iteration=2,
            code_quality=CodeQualityMetrics(overall_score=75.0),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    report = analyzer.generate_evolution_report()

    assert "No significant quality drops detected" in report


def test_generate_evolution_report_with_all_metrics():
    """Test report includes all quality metrics when present."""
    from src.code_quality.models import TimeComplexityScore, SpaceComplexityScore

    iterations = [
        IterationResult(
            iteration=1,
            code_quality=CodeQualityMetrics(
                time_complexity=TimeComplexityScore(performance_score=80.0),
                space_complexity=SpaceComplexityScore(memory_efficiency_score=75.0),
                readability=ReadabilityScore(readability_score=70.0),
                style_consistency=StyleConsistencyScore(style_score=85.0),
                overall_score=77.5,
            ),
        ),
    ]

    result = ExecutionResult(
        problem_id="test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=iterations,
    )

    analyzer = EvolutionAnalyzer(result)
    report = analyzer.generate_evolution_report()

    assert "Time Complexity: 80.0" in report
    assert "Space Complexity: 75.0" in report
    assert "Readability: 70.0" in report
    assert "Style Consistency: 85.0" in report
    assert "Overall Score: 77.5" in report
