"""
Main Code Quality Analyzer

Orchestrates all code quality analysis dimensions.
"""

from typing import Optional

from src.code_quality.models import CodeQualityMetrics
from src.code_quality.readability_analyzer import ReadabilityAnalyzer
from src.code_quality.space_analyzer import SpaceAnalyzer
from src.code_quality.style_analyzer import StyleConsistencyAnalyzer
from src.code_quality.time_analyzer import TimeComplexityAnalyzer
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


class CodeQualityAnalyzer:
    """Main orchestrator for code quality analysis."""

    def __init__(
        self,
        enable_time: bool = True,
        enable_space: bool = True,
        enable_readability: bool = True,
        enable_style: bool = True,
    ):
        """
        Initialize code quality analyzer.

        Args:
            enable_time: Enable time complexity analysis
            enable_space: Enable space complexity analysis
            enable_readability: Enable readability analysis
            enable_style: Enable style consistency analysis
        """
        self.enable_time = enable_time
        self.enable_space = enable_space
        self.enable_readability = enable_readability
        self.enable_style = enable_style

        # Initialize analyzers
        self.time_analyzer = TimeComplexityAnalyzer() if enable_time else None
        self.space_analyzer = SpaceAnalyzer() if enable_space else None
        self.readability_analyzer = ReadabilityAnalyzer() if enable_readability else None
        self.style_analyzer = StyleConsistencyAnalyzer() if enable_style else None

    def analyze(
        self, code: str, problem: Optional[Problem] = None, sandbox_executor=None
    ) -> CodeQualityMetrics:
        """
        Perform comprehensive code quality analysis.

        Args:
            code: Python code to analyze
            problem: Problem definition (optional, for performance testing)
            sandbox_executor: Optional SandboxExecutor for safe code execution
                            (required for time/space performance profiling)

        Returns:
            CodeQualityMetrics with all analysis results
        """
        errors = []

        # Time complexity analysis
        time_result = None
        if self.enable_time and self.time_analyzer:
            try:
                time_result = self.time_analyzer.analyze(code, problem, sandbox_executor)
            except Exception as e:
                logger.warning("time_analysis_error", error=str(e))
                errors.append(f"Time complexity analysis failed: {str(e)}")

        # Space complexity analysis
        space_result = None
        if self.enable_space and self.space_analyzer:
            try:
                space_result = self.space_analyzer.analyze(code, sandbox_executor=sandbox_executor)
            except Exception as e:
                logger.warning("space_analysis_error", error=str(e))
                errors.append(f"Space complexity analysis failed: {str(e)}")

        # Readability analysis
        readability_result = None
        if self.enable_readability and self.readability_analyzer:
            try:
                readability_result = self.readability_analyzer.analyze(code)
            except Exception as e:
                logger.warning("readability_analysis_error", error=str(e))
                errors.append(f"Readability analysis failed: {str(e)}")

        # Style consistency analysis
        style_result = None
        if self.enable_style and self.style_analyzer:
            try:
                style_result = self.style_analyzer.analyze(code)
            except Exception as e:
                logger.warning("style_analysis_error", error=str(e))
                errors.append(f"Style consistency analysis failed: {str(e)}")

        # Create metrics object
        metrics = CodeQualityMetrics(
            time_complexity=time_result,
            space_complexity=space_result,
            readability=readability_result,
            style_consistency=style_result,
            overall_score=None,
            analysis_errors=errors,
        )

        # Calculate overall score
        metrics.overall_score = metrics.calculate_overall_score()

        return metrics
