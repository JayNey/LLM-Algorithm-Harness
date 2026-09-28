"""
Test suite for code quality analyzers.
"""

import pytest

from src.code_quality.analyzer import CodeQualityAnalyzer
from src.code_quality.time_analyzer import TimeComplexityAnalyzer
from src.code_quality.space_analyzer import SpaceAnalyzer
from src.code_quality.readability_analyzer import ReadabilityAnalyzer
from src.code_quality.style_analyzer import StyleConsistencyAnalyzer


class TestTimeComplexityAnalyzer:
    """Tests for time complexity analyzer."""

    def test_analyze_simple_code(self):
        """Test analyzing simple linear code."""
        analyzer = TimeComplexityAnalyzer()
        code = """
def solution(n):
    result = 0
    for i in range(n):
        result += i
    return result
"""
        result = analyzer.analyze(code, sandbox_executor=None)
        assert result.loop_nesting_depth == 1
        assert result.static_analysis == "O(n)"

    def test_analyze_nested_loops(self):
        """Test analyzing nested loops."""
        analyzer = TimeComplexityAnalyzer()
        code = """
def solution(matrix):
    for i in range(len(matrix)):
        for j in range(len(matrix[0])):
            print(matrix[i][j])
"""
        result = analyzer.analyze(code, sandbox_executor=None)
        assert result.loop_nesting_depth == 2
        assert result.static_analysis == "O(n^2)"

    def test_analyze_no_loops(self):
        """Test analyzing constant time code."""
        analyzer = TimeComplexityAnalyzer()
        code = """
def solution(x):
    return x * 2
"""
        result = analyzer.analyze(code, sandbox_executor=None)
        assert result.loop_nesting_depth == 0
        assert result.static_analysis == "O(1)"


class TestSpaceComplexityAnalyzer:
    """Tests for space complexity analyzer."""

    def test_analyze_requires_sandbox(self):
        """Test that space analyzer requires sandbox executor."""
        analyzer = SpaceAnalyzer()
        code = "def solution(x): return x"
        result = analyzer.analyze(code, sandbox_executor=None)
        assert "requires sandbox" in result.analysis_notes[0].lower()


class TestReadabilityAnalyzer:
    """Tests for readability analyzer."""

    def test_analyze_clean_code(self):
        """Test analyzing clean, readable code."""
        analyzer = ReadabilityAnalyzer()
        code = """
def add_numbers(a, b):
    \"\"\"Add two numbers and return the result.\"\"\"
    return a + b
"""
        result = analyzer.analyze(code)
        # Should have some readability metrics
        assert result.readability_score is not None or result.pylint_score is not None


class TestStyleConsistencyAnalyzer:
    """Tests for style consistency analyzer."""

    def test_analyze_formatted_code(self):
        """Test analyzing properly formatted code."""
        analyzer = StyleConsistencyAnalyzer()
        code = """
def hello():
    print("Hello, World!")
"""
        result = analyzer.analyze(code)
        assert result.style_score is not None


class TestCodeQualityAnalyzer:
    """Tests for main code quality analyzer."""

    def test_full_analysis(self):
        """Test full code quality analysis."""
        analyzer = CodeQualityAnalyzer()
        code = "def solution(x): return x"
        result = analyzer.analyze(code, sandbox_executor=None)
        assert result.time_complexity is not None
        assert result.overall_score is not None

    def test_analysis_with_disabled_dimensions(self):
        """Test analysis with some dimensions disabled."""
        analyzer = CodeQualityAnalyzer(
            enable_time=True,
            enable_space=False,
            enable_readability=False,
            enable_style=False,
        )
        code = "def solution(x): return x"
        result = analyzer.analyze(code, sandbox_executor=None)
        assert result.time_complexity is not None
        assert result.space_complexity is None
        assert result.readability is None
        assert result.style_consistency is None
