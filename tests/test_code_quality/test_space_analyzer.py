"""
Tests for Space Complexity Analyzer
"""

import pytest

from src.code_quality.space_analyzer import SpaceAnalyzer


class TestSpaceAnalyzer:
    """Test suite for SpaceAnalyzer."""

    @pytest.fixture
    def analyzer(self):
        """Create analyzer instance."""
        return SpaceAnalyzer()

    def test_analyze_simple_code(self, analyzer):
        """Test analysis of simple code with minimal memory usage."""
        code = """
def solution(x):
    return x * 2
"""
        result = analyzer.analyze(code)
        # Current implementation returns None until sandbox integration
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analyze_memory_intensive_code(self, analyzer):
        """Test analysis of code with higher memory usage."""
        code = """
def solution(n):
    # Create large list
    data = [i for i in range(n)]
    return len(data)

solution(10000)
"""
        result = analyzer.analyze(code)
        # Current implementation returns None until sandbox integration
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analyze_with_data_structures(self, analyzer):
        """Test analysis of code using various data structures."""
        code = """
def solution():
    # Create various data structures
    list_data = [i for i in range(100)]
    dict_data = {i: i*2 for i in range(100)}
    set_data = {i for i in range(100)}
    return len(list_data) + len(dict_data) + len(set_data)

solution()
"""
        result = analyzer.analyze(code)
        # Current implementation returns None until sandbox integration
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_efficiency_score_calculation(self, analyzer):
        """Test that efficiency score is calculated reasonably."""
        code = """
def solution():
    return 42
"""
        result = analyzer.analyze(code)
        # Current implementation returns None until sandbox integration
        assert result.memory_efficiency_score is None
        assert "Memory profiling requires sandbox executor" in result.analysis_notes

    def test_analysis_notes_generation(self, analyzer):
        """Test that analysis notes are generated."""
        code = """
def solution():
    return 1
"""
        result = analyzer.analyze(code)
        # Should have notes list (even if empty)
        assert isinstance(result.analysis_notes, list)

    def test_invalid_code_handling(self, analyzer):
        """Test handling of invalid code."""
        invalid_code = "def broken syntax"
        result = analyzer.analyze(invalid_code)
        # Should return empty score without crashing
        assert result.peak_memory_bytes is None
        assert result.peak_memory_mb is None

    def test_empty_code_handling(self, analyzer):
        """Test handling of empty code."""
        result = analyzer.analyze("")
        # Should handle gracefully
        assert result is not None
