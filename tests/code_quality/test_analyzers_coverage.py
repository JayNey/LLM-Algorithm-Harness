"""Tests for code quality analyzers (time and space complexity)."""

from unittest.mock import MagicMock

import pytest

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
        assert "Memory profiling requires sandbox executor" in score.analysis_notes

    def _sandbox(self, payload):
        sandbox = MagicMock()
        sandbox.execute_with_memory_profiling.return_value = payload
        return sandbox

    def test_successful_profiling_low_memory(self):
        sandbox = self._sandbox({"success": True, "peak_memory_bytes": 512 * 1024})
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert isinstance(score, SpaceComplexityScore)
        assert score.peak_memory_mb == 0.5
        assert score.memory_efficiency_score == 100.0
        assert "Very efficient memory usage" in score.analysis_notes

    def test_high_memory_notes(self):
        sandbox = self._sandbox({"success": True, "peak_memory_bytes": 60 * 1024 * 1024})
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert score.memory_efficiency_score == pytest.approx(
            100.0 - ((60 - 10) / 90 * 100), abs=0.01
        )
        assert "High memory usage detected" in score.analysis_notes

    def test_over_100mb_scores_zero(self):
        sandbox = self._sandbox({"success": True, "peak_memory_bytes": 200 * 1024 * 1024})
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert score.memory_efficiency_score == 0.0

    def test_failed_profiling(self):
        sandbox = self._sandbox({"success": False, "error": "sandbox exploded"})
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert score.peak_memory_bytes is None
        assert "Memory profiling failed: sandbox exploded" in score.analysis_notes

    def test_missing_peak_data(self):
        sandbox = self._sandbox({"success": True})
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert "Memory profiling data unavailable" in score.analysis_notes

    def test_profiling_exception_is_contained(self):
        sandbox = MagicMock()
        sandbox.execute_with_memory_profiling.side_effect = OSError("disk full")
        score = SpaceAnalyzer().analyze(SAMPLE_CODE, "1", sandbox_executor=sandbox)
        assert "Memory profiling error" in score.analysis_notes[0]


class TestTimeAnalyzer:
    def test_static_analysis_without_problem(self):
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE)
        assert score.loop_nesting_depth == 0
        assert score.execution_times == {}

    def test_performance_profiling_success(self):
        problem = make_problem()
        sandbox = MagicMock()
        sandbox.execute_with_performance_profiling.return_value = {
            "success": True,
            "execution_times": {"n=10": 0.01, "n=100": 0.1},
            "is_timeout": False,
        }
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE, problem, sandbox_executor=sandbox)
        assert score.execution_times == {"n=10": 0.01, "n=100": 0.1}
        assert score.is_timeout is False

    def test_performance_profiling_failure_is_contained(self):
        problem = make_problem()
        sandbox = MagicMock()
        sandbox.execute_with_performance_profiling.return_value = {
            "success": False,
            "error": "profiler exploded",
        }
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE, problem, sandbox_executor=sandbox)
        assert score.execution_times == {}

    def test_profiling_exception_is_contained(self):
        problem = make_problem()
        sandbox = MagicMock()
        sandbox.execute_with_performance_profiling.side_effect = OSError("blocked")
        analyzer = TimeComplexityAnalyzer()
        score = analyzer.analyze(SAMPLE_CODE, problem, sandbox_executor=sandbox)
        assert score.execution_times == {}
        assert score.is_timeout is False
