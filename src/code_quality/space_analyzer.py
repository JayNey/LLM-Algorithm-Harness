"""
Space Complexity Analyzer

Analyzes memory usage through sandbox-isolated memory profiling.
SECURITY: Uses SandboxExecutor for safe code execution - never executes untrusted code directly.
"""

from typing import Optional

from src.code_quality.models import SpaceComplexityScore
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SpaceAnalyzer:
    """Analyzes space complexity through memory profiling."""

    def analyze(
        self, code: str, test_input: str = "", sandbox_executor=None
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

            # Use sandbox executor for safe memory profiling
            try:
                result = sandbox_executor.execute_with_memory_profiling(
                    code=code, test_input=test_input, timeout=10
                )

                if not result.get("success"):
                    logger.debug("sandbox_memory_profiling_failed", error=result.get("error"))
                    return SpaceComplexityScore(
                        analysis_notes=[
                            f"Memory profiling failed: {result.get('error', 'unknown')}"
                        ]
                    )

                peak = result.get("peak_memory_bytes")
                if peak is None:
                    return SpaceComplexityScore(
                        analysis_notes=["Memory profiling data unavailable"]
                    )

                peak_mb = peak / (1024 * 1024)

                # Calculate efficiency score (lower memory = higher score)
                # Baseline: < 10MB = 100, > 100MB = 0
                if peak_mb < 10:
                    efficiency_score = 100.0
                elif peak_mb > 100:
                    efficiency_score = 0.0
                else:
                    efficiency_score = 100.0 - ((peak_mb - 10) / 90 * 100)

                # Generate analysis notes
                notes = []
                if peak_mb > 50:
                    notes.append("High memory usage detected")
                if peak_mb < 1:
                    notes.append("Very efficient memory usage")

                return SpaceComplexityScore(
                    peak_memory_bytes=peak,
                    peak_memory_mb=round(peak_mb, 2),
                    memory_efficiency_score=round(efficiency_score, 2),
                    analysis_notes=notes,
                )

            except Exception as e:
                logger.warning("sandbox_memory_profiling_failed", error=str(e))
                return SpaceComplexityScore(analysis_notes=[f"Memory profiling error: {str(e)}"])

        except Exception as e:
            logger.warning("space_analysis_failed", error=str(e))
            return SpaceComplexityScore()
