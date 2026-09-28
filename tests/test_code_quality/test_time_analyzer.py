"""
Tests for Time Complexity Analyzer
"""

import pytest

from src.code_quality.time_analyzer import TimeComplexityAnalyzer


class TestTimeComplexityAnalyzer:
    """Test suite for TimeComplexityAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return TimeComplexityAnalyzer()

    def test_constant_time_complexity(self, analyzer):
        """Test O(1) complexity detection."""
        code = """
def solution(x):
    return x * 2
"""
        result = analyzer.analyze(code)
        assert result.static_analysis == "O(1)"
        assert result.loop_nesting_depth == 0
        assert result.performance_score >= 90.0

    def test_linear_time_complexity(self, analyzer):
        """Test O(n) complexity detection."""
        code = """
def solution(arr):
    total = 0
    for x in arr:
        total += x
    return total
"""
        result = analyzer.analyze(code)
        assert result.static_analysis == "O(n)"
        assert result.loop_nesting_depth == 1
        assert result.performance_score >= 70.0

    def test_quadratic_time_complexity(self, analyzer):
        """Test O(n^2) complexity detection."""
        code = """
def solution(matrix):
    result = 0
    for row in matrix:
        for item in row:
            result += item
    return result
"""
        result = analyzer.analyze(code)
        assert result.static_analysis == "O(n^2)"
        assert result.loop_nesting_depth == 2
        assert result.performance_score >= 40.0
        assert result.performance_score < 80.0

    def test_cubic_time_complexity(self, analyzer):
        """Test O(n^3) complexity detection."""
        code = """
def solution(cube):
    result = 0
    for plane in cube:
        for row in plane:
            for item in row:
                result += item
    return result
"""
        result = analyzer.analyze(code)
        assert result.static_analysis == "O(n^3)"
        assert result.loop_nesting_depth == 3
        assert result.performance_score < 60.0

    def test_nested_loops_with_condition(self, analyzer):
        """Test complexity with nested loops and conditions."""
        code = """
def solution(arr):
    result = []
    for i in arr:
        for j in arr:
            if i + j > 10:
                result.append(i + j)
    return result
"""
        result = analyzer.analyze(code)
        assert result.loop_nesting_depth == 2
        assert result.static_analysis == "O(n^2)"

    def test_while_loop_detection(self, analyzer):
        """Test detection of while loops."""
        code = """
def solution(n):
    count = 0
    while n > 0:
        count += 1
        n //= 2
    return count
"""
        result = analyzer.analyze(code)
        assert result.loop_nesting_depth == 1
        assert result.static_analysis == "O(n)"

    def test_mixed_loop_types(self, analyzer):
        """Test detection of mixed for and while loops."""
        code = """
def solution(arr):
    result = 0
    for item in arr:
        n = item
        while n > 0:
            result += n
            n -= 1
    return result
"""
        result = analyzer.analyze(code)
        assert result.loop_nesting_depth == 2
        assert result.static_analysis == "O(n^2)"

    def test_invalid_code_handling(self, analyzer):
        """Test handling of invalid code."""
        invalid_code = "def broken syntax"
        result = analyzer.analyze(invalid_code)
        # Invalid code should return a result, but might have O(1) as fallback
        assert result.loop_nesting_depth == 0
        # Static analysis might be None or O(1) depending on error handling
        assert result.static_analysis in [None, "O(1)"]

    def test_empty_code_handling(self, analyzer):
        """Test handling of empty code."""
        result = analyzer.analyze("")
        assert result.static_analysis == "O(1)"
        assert result.loop_nesting_depth == 0

    def test_performance_score_range(self, analyzer):
        """Test that performance scores are in valid range."""
        codes = [
            "def f(x): return x",  # O(1)
            "def f(arr):\n    for x in arr: pass",  # O(n)
            "def f(m):\n    for r in m:\n        for c in r: pass",  # O(n^2)
        ]
        for code in codes:
            result = analyzer.analyze(code)
            assert 0.0 <= result.performance_score <= 100.0

    def test_timeout_handling(self, analyzer):
        """Test timeout scenario handling."""
        result = analyzer._calculate_performance_score(
            loop_depth=2, growth_rate=None, is_timeout=True
        )
        assert result == 0.0

    def test_growth_rate_impact(self, analyzer):
        """Test that growth rate affects performance score."""
        # Low growth rate should give better score
        score_low = analyzer._calculate_performance_score(
            loop_depth=1, growth_rate=1.5, is_timeout=False
        )
        # High growth rate should give worse score
        score_high = analyzer._calculate_performance_score(
            loop_depth=1, growth_rate=500.0, is_timeout=False
        )
        assert score_low > score_high
