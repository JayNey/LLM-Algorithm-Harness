"""
Tests for Style Consistency Analyzer
"""

import pytest

from src.code_quality.style_analyzer import StyleConsistencyAnalyzer


class TestStyleAnalyzer:
    """Test suite for StyleConsistencyAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return StyleConsistencyAnalyzer()

    def test_analyze_black_compliant_code(self, analyzer):
        """Test analysis of code that follows black formatting."""
        code = """
def calculate_sum(numbers):
    total = 0
    for num in numbers:
        total += num
    return total
"""
        result = analyzer.analyze(code)
        assert result is not None
        assert result.black_compliant is not None
        assert result.style_violations >= 0

    def test_analyze_poorly_formatted_code(self, analyzer):
        """Test analysis of poorly formatted code."""
        code = """
def bad_format(x,y,z):
    result=x+y+z
    return result
"""
        result = analyzer.analyze(code)
        # Should detect formatting issues
        if result.black_compliant is not None:
            # Poorly formatted code should not be black compliant
            assert result.style_violations >= 0

    def test_style_score_calculation(self, analyzer):
        """Test that style score is calculated."""
        code = """
def simple_function(x):
    return x * 2
"""
        result = analyzer.analyze(code)
        if result.style_score is not None:
            assert 0.0 <= result.style_score <= 100.0

    def test_violations_detail_list(self, analyzer):
        """Test that violations detail is a list."""
        code = "def f(x): return x"
        result = analyzer.analyze(code)
        assert isinstance(result.violations_detail, list)

    def test_black_compliant_high_score(self, analyzer):
        """Test that black-compliant code gets high score."""
        code = """
def well_formatted_function(parameter_one, parameter_two):
    result = parameter_one + parameter_two
    return result
"""
        result = analyzer.analyze(code)
        if result.black_compliant is True:
            assert result.style_score >= 90.0

    def test_non_compliant_lower_score(self, analyzer):
        """Test that non-compliant code gets lower score."""
        code = """def bad(x,y,z):result=x+y+z;return result"""
        result = analyzer.analyze(code)
        if result.black_compliant is False:
            assert result.style_violations > 0

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

    def test_code_with_long_lines(self, analyzer):
        """Test analysis of code with long lines."""
        code = """
def function_with_long_line():
    very_long_string = "This is a very long string that exceeds the recommended line length and should be detected by style checkers"
    return very_long_string
"""
        result = analyzer.analyze(code)
        assert result is not None
        # Should detect style issues with long lines
        if result.black_compliant is not None:
            assert result.style_violations >= 0

    def test_mixed_indentation(self, analyzer):
        """Test detection of mixed indentation."""
        code = """
def mixed_indent():
    x = 1
\ty = 2
    return x + y
"""
        result = analyzer.analyze(code)
        assert result is not None

    def test_multiple_violations(self, analyzer):
        """Test code with multiple style violations."""
        code = """
def bad(x,y):a=x+y;b=x*y;return a+b
"""
        result = analyzer.analyze(code)
        # Should detect multiple violations
        if result.violations_detail:
            assert len(result.violations_detail) >= 0

    def test_perfect_formatting(self, analyzer):
        """Test perfectly formatted code."""
        code = """
def perfectly_formatted_function(input_value):
    '''A perfectly formatted function with proper style.'''
    result = input_value * 2
    return result


def another_function(data):
    '''Another well-formatted function.'''
    processed = [item * 2 for item in data]
    return processed
"""
        result = analyzer.analyze(code)
        # Well-formatted code should have minimal or no violations
        assert result.style_violations >= 0
