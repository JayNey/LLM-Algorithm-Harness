"""Tests for code quality analyzers (current upstream placeholder behavior)."""

from unittest.mock import MagicMock

from src.code_quality.models import SpaceComplexityScore
from src.code_quality.space_analyzer import SpaceAnalyzer
from src.code_quality.time_analyzer import TimeComplexityAnalyzer

SAMPLE_CODE = "def solution(x):\n    return x + 1\n"


def make_problem():
    from src.models import Problem, TestCase

    return Problem(
        problem_id="p1",
        title="P1",
        description="A problem description long enough",
        difficulty="easy",
        tags=["tag"],
        test_cases=[TestCase(input={"x": 1}, expected_output=1)],
    )


class TestSpaceAnalyzer:
    def test_requires_sandbox_executor(self):
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, sandbox_executor=None)
        assert isinstance(score, SpaceComplexityScore)
        assert "Memory profiling requires sandbox executor" in score.analysis_notes

    def test_sandbox_provided_returns_placeholder(self):
        """Upstream defers real profiling (needs Problem context); the
        analyzer returns an explicit placeholder instead of guessing."""
        sandbox = MagicMock()
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert "Memory profiling not available without Problem context" in score.analysis_notes
        assert score.peak_memory_bytes is None
        sandbox.execute_with_memory_profiling.assert_not_called()

    def test_default_score_has_no_notes(self):
        score = SpaceComplexityScore()
        assert score.analysis_notes == []
        assert score.peak_memory_bytes is None


class TestTimeComplexityAnalyzer:
    def test_static_analysis_without_problem(self):
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE)
        assert score.loop_nesting_depth == 0
        assert score.execution_times == {}
        assert score.is_timeout is False

    def test_performance_profiling_deferred_returns_empty(self):
        """Upstream defers performance profiling (sandbox API mismatch); the
        analyzer degrades to static-only results without raising."""
        problem = make_problem()
        sandbox = MagicMock()
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE, problem, sandbox_executor=sandbox)
        assert score.execution_times == {}
        assert score.measured_growth_rate is None
        assert score.is_timeout is False
        sandbox.execute_with_performance_profiling.assert_not_called()

    def test_loop_nesting_detected(self):
        analyzer = TimeComplexityAnalyzer()
        nested = (
            "def solution(rows):\n"
            "    total = 0\n"
            "    for row in rows:\n"
            "        for item in row:\n"
            "            total += item\n"
            "    return total\n"
        )
        score = analyzer.analyze(nested)
        assert score.loop_nesting_depth >= 2
