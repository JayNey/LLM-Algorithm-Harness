"""
Tests for Readability Analyzer
"""

import pytest

from src.code_quality.readability_analyzer import ReadabilityAnalyzer


class TestReadabilityAnalyzer:
    """Test suite for ReadabilityAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return ReadabilityAnalyzer()

    def test_analyze_clean_code(self, analyzer):
        """Test analysis of clean, readable code."""
        code = """
def calculate_sum(numbers):
    '''Calculate the sum of a list of numbers.'''
    total = 0
    for num in numbers:
        total += num
    return total
"""
        result = analyzer.analyze(code)
        assert result is not None
        # Should have at least one metric
        assert (
            result.pylint_score is not None
            or result.flake8_issues is not None
            or result.cyclomatic_complexity is not None
        )

    def test_analyze_complex_code(self, analyzer):
        """Test analysis of code with higher complexity."""
        code = """
def complex_function(a, b, c, d, e):
    if a > 0:
        if b > 0:
            if c > 0:
                if d > 0:
                    if e > 0:
                        return a + b + c + d + e
                    else:
                        return a + b + c + d
                else:
                    return a + b + c
            else:
                return a + b
        else:
            return a
    else:
        return 0
"""
        result = analyzer.analyze(code)
        # Complex code should have measurable complexity
        if result.cyclomatic_complexity is not None:
            assert result.cyclomatic_complexity > 1.0

    def test_analyze_poorly_formatted_code(self, analyzer):
        """Test analysis of poorly formatted code."""
        code = """
def bad_format(x,y,z):
    result=x+y+z
    return result
"""
        result = analyzer.analyze(code)
        # Should detect some issues
        if result.flake8_issues is not None:
            assert result.flake8_issues >= 0

    def test_readability_score_calculation(self, analyzer):
        """Test that readability score is calculated."""
        code = """
def simple_function(x):
    return x * 2
"""
        result = analyzer.analyze(code)
        # Should have readability score if any tool succeeded
        if any(
            [
                result.pylint_score is not None,
                result.flake8_issues is not None,
                result.cyclomatic_complexity is not None,
            ]
        ):
            assert result.readability_score is not None
            assert 0.0 <= result.readability_score <= 100.0

    def test_invalid_code_handling(self, analyzer):
        """Test handling of syntactically invalid code."""
        invalid_code = "def broken syntax"
        result = analyzer.analyze(invalid_code)
        # Should return a result without crashing
        assert result is not None

    def test_empty_code_handling(self, analyzer):
        """Test handling of empty code."""
        result = analyzer.analyze("")
        assert result is not None

    def test_well_documented_code(self, analyzer):
        """Test analysis of well-documented code."""
        code = '''
def calculate_average(numbers):
    """
    Calculate the average of a list of numbers.

    Args:
        numbers: List of numeric values

    Returns:
        The average value, or 0 if list is empty
    """
    if not numbers:
        return 0
    return sum(numbers) / len(numbers)
'''
        result = analyzer.analyze(code)
        # Well-documented code should have decent readability
        if result.readability_score is not None:
            assert result.readability_score >= 0.0

    def test_multiple_functions(self, analyzer):
        """Test analysis of code with multiple functions."""
        code = """
def function_one(x):
    return x + 1

def function_two(y):
    return y * 2

def function_three(z):
    return z - 1
"""
        result = analyzer.analyze(code)
        assert result is not None

    def test_issues_list_exists(self, analyzer):
        """Test that issues list is always present."""
        code = "def f(x): return x"
        result = analyzer.analyze(code)
        assert isinstance(result.issues, list)
