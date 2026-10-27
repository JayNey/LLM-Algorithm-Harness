"""
Space Complexity Analyzer

Analyzes memory usage through sandbox-isolated memory profiling.
SECURITY: Uses SandboxExecutor for safe code execution - never executes untrusted code directly.
"""

from typing import TYPE_CHECKING

from src.code_quality.models import SpaceComplexityScore
from src.models import Problem
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.sandbox_executor import SandboxExecutor

logger = get_logger(__name__)


class SpaceAnalyzer:
    """Analyzes space complexity through memory profiling."""

    def analyze(
        self,
        code: str,
        test_input: str = "",
        sandbox_executor: "SandboxExecutor | None" = None,
        *,
        problem: Problem | None = None,
    ) -> SpaceComplexityScore:
        """
        Analyze space complexity using sandbox executor for safe execution.

        Args:
            code: Python code to analyze
            test_input: Legacy argument retained for compatibility; profiling uses problem.public_test_cases
            problem: Problem definition including entry protocol and public tests
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

            if problem is None:
                return SpaceComplexityScore(
                    analysis_notes=["Memory profiling not available without Problem context"]
                )
            samples = sandbox_executor.execute_with_memory_profiling(code, problem, scales=[1])
            if not samples:
                return SpaceComplexityScore(
                    analysis_notes=[
                        "No valid memory samples: execution failed, unsupported, or no public tests"
                    ]
                )
            peak = samples[1]["peak_bytes"]
            if type(peak) is not int or peak < 0:
                raise ValueError("Invalid memory peak")
            budget = sandbox_executor.config.memory_limit_mb * 1024 * 1024
            efficiency = round(max(0.0, min(100.0, 100 * (1 - peak / budget))), 2)
            return SpaceComplexityScore(
                peak_memory_bytes=peak,
                peak_memory_mb=peak / (1024 * 1024),
                memory_efficiency_score=efficiency,
                analysis_notes=[
                    "Peak Python allocations measured with tracemalloc inside the sandbox runner over public tests",
                    "Includes code loading and runner overhead; excludes interpreter startup and untracked native allocations; not process RSS or inferred Big-O",
                    f"Memory budget headroom score: 100 * (1 - peak / budget); budget={budget} bytes",
                ],
            )

        except Exception as e:
            logger.warning("space_analysis_failed", error=str(e))
            return SpaceComplexityScore(
                analysis_notes=["Memory profiling failed; no valid measurement"]
            )
