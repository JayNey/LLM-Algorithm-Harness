"""
Space Complexity Analyzer

Analyzes memory usage through sandbox-isolated memory profiling.
SECURITY: Uses SandboxExecutor for safe code execution - never executes untrusted code directly.
"""

from typing import TYPE_CHECKING

from src.code_quality.models import SpaceComplexityScore
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.sandbox_executor import SandboxExecutor

logger = get_logger(__name__)


class SpaceAnalyzer:
    """Analyzes space complexity through memory profiling."""

    def analyze(
        self, code: str, test_input: str = "", sandbox_executor: "SandboxExecutor | None" = None
    ) -> SpaceComplexityScore:
        """
        Analyze space complexity using sandbox executor for safe execution.

        Args:
            code: Python code to analyze
            test_input: Optional test input for execution
            sandbox_executor: Optional SandboxExecutor instance for safe memory profiling

        Returns:
            SpaceComplexityScore with memory usage metrics
        """
        try:
            # Require sandbox executor for safe execution
            if sandbox_executor is None:
                logger.info("space_analysis_requires_sandbox")
                return SpaceComplexityScore(
                    analysis_notes=["Memory profiling requires sandbox executor"]
                )

            # Note: The current implementation of execute_with_memory_profiling
            # requires a Problem object, but we don't have one here.
            # This is a design mismatch that needs to be addressed.
            # For now, return a placeholder result.
            logger.info("space_analysis_not_implemented")
            return SpaceComplexityScore(
                analysis_notes=["Memory profiling not available without Problem context"]
            )

        except Exception as e:
            logger.warning("space_analysis_failed", error=str(e))
            return SpaceComplexityScore()
