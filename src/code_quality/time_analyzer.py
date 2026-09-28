"""
Time Complexity Analyzer

Analyzes code time complexity through:
- Static analysis (AST-based loop nesting detection) - safe, no code execution
- Performance testing (execution at different scales) - requires SandboxExecutor for safety
- Complexity inference from growth rate

SECURITY: Performance testing uses SandboxExecutor for safe code execution.
"""

import ast
from typing import Any, Dict, Optional

from src.code_quality.models import TimeComplexityScore
from src.models import Problem
from src.utils.logging import get_logger

logger = get_logger(__name__)


class TimeComplexityAnalyzer:
    """Analyzes time complexity of generated code."""

    def __init__(self, timeout_seconds: float = 5.0):
        """
        Initialize analyzer.

        Args:
            timeout_seconds: Maximum time allowed per scale test
        """
        self.timeout_seconds = timeout_seconds

    def analyze(
        self, code: str, problem: Optional[Problem] = None, sandbox_executor=None
    ) -> TimeComplexityScore:
        """
        Analyze time complexity of code.

        Args:
            code: Python code to analyze
            problem: Problem definition (for performance testing)
            sandbox_executor: Optional SandboxExecutor for safe performance testing

        Returns:
            TimeComplexityScore with analysis results
        """
        try:
            # Static analysis (safe - no code execution)
            loop_depth = self._analyze_loop_nesting(code)
            static_complexity = self._infer_complexity_from_depth(loop_depth)

            # Performance testing (requires sandbox executor for safety)
            execution_times: Dict[str, float] = {}
            measured_growth = None
            is_timeout = False

            if problem and problem.test_cases and sandbox_executor is not None:
                execution_times, is_timeout = self._performance_test(
                    code, problem, sandbox_executor
                )
                if execution_times and len(execution_times) >= 2:
                    measured_growth = self._calculate_growth_rate(execution_times)

            # Calculate performance score
            perf_score = self._calculate_performance_score(loop_depth, measured_growth, is_timeout)

            return TimeComplexityScore(
                static_analysis=static_complexity,
                loop_nesting_depth=loop_depth,
                measured_growth_rate=measured_growth,
                is_timeout=is_timeout,
                execution_times=execution_times,
                performance_score=perf_score,
            )

        except Exception as e:
            logger.warning("time_complexity_analysis_failed", error=str(e))
            return TimeComplexityScore(
                static_analysis=None,
                loop_nesting_depth=0,
                measured_growth_rate=None,
                is_timeout=False,
                execution_times={},
                performance_score=None,
            )

    def _analyze_loop_nesting(self, code: str) -> int:
        """
        Analyze loop nesting depth using AST.

        Args:
            code: Python code to analyze

        Returns:
            Maximum loop nesting depth
        """
        try:
            tree = ast.parse(code)
            return self._max_loop_depth(tree)
        except SyntaxError:
            return 0

    def _max_loop_depth(self, node: ast.AST, current_depth: int = 0) -> int:
        """Recursively calculate maximum loop nesting depth."""
        max_depth = current_depth

        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.For, ast.While)):
                # Found a loop, increase depth and recurse
                child_depth = self._max_loop_depth(child, current_depth + 1)
                max_depth = max(max_depth, child_depth)
            else:
                # Not a loop, continue recursing without increasing depth
                child_depth = self._max_loop_depth(child, current_depth)
                max_depth = max(max_depth, child_depth)

        return max_depth

    def _infer_complexity_from_depth(self, depth: int) -> str:
        """Infer Big-O complexity from loop nesting depth."""
        if depth == 0:
            return "O(1)"
        elif depth == 1:
            return "O(n)"
        elif depth == 2:
            return "O(n^2)"
        elif depth == 3:
            return "O(n^3)"
        else:
            return f"O(n^{depth})"

    def _performance_test(
        self, code: str, problem: Problem, sandbox_executor
    ) -> tuple[Dict[str, float], bool]:
        """
        Run performance tests at different scales using sandbox executor.

        Args:
            code: Code to test
            problem: Problem with test cases
            sandbox_executor: SandboxExecutor for safe execution

        Returns:
            (execution_times, is_timeout)
        """
        execution_times: Dict[str, float] = {}
        is_timeout = False

        try:
            # Use sandbox executor for safe performance profiling
            result = sandbox_executor.execute_with_performance_profiling(
                code=code, problem=problem, timeout=self.timeout_seconds
            )

            if result.get("success"):
                execution_times = result.get("execution_times", {})
                is_timeout = result.get("is_timeout", False)
            else:
                logger.debug("performance_profiling_failed", error=result.get("error"))

        except Exception as e:
            logger.warning("performance_test_failed", error=str(e))

        return execution_times, is_timeout

    def _calculate_growth_rate(self, execution_times: Dict[str, float]) -> float:
        """Calculate empirical growth rate from execution times."""
        if len(execution_times) < 2:
            return 1.0

        # Simple growth rate calculation
        times = sorted(execution_times.items())
        if len(times) >= 2:
            return times[-1][1] / times[0][1]
        return 1.0

    def _calculate_performance_score(
        self, loop_depth: int, growth_rate: Optional[float], is_timeout: bool
    ) -> float:
        """
        Calculate overall performance score (0-100).

        Scoring criteria:
        - O(1): 95-100 (constant time is ideal)
        - O(log n): 90-95 (logarithmic is excellent)
        - O(n): 80-90 (linear is good)
        - O(n log n): 70-80 (linearithmic is acceptable)
        - O(n^2): 50-70 (quadratic is moderate)
        - O(n^3): 30-50 (cubic is poor)
        - O(2^n): 0-30 (exponential is very poor)
        """
        if is_timeout:
            return 0.0

        # Base score on loop depth (static analysis)
        if loop_depth == 0:
            base_score = 97.5  # O(1)
        elif loop_depth == 1:
            base_score = 85.0  # O(n)
        elif loop_depth == 2:
            base_score = 60.0  # O(n^2)
        elif loop_depth == 3:
            base_score = 40.0  # O(n^3)
        elif loop_depth >= 4:
            base_score = max(10.0, 50.0 - (loop_depth * 10))
        else:
            base_score = 50.0

        # Adjust based on measured growth rate (empirical data)
        if growth_rate is not None:
            if growth_rate < 2.0:
                # Sub-linear or constant growth
                growth_multiplier = 1.1
            elif growth_rate < 10.0:
                # Linear to log-linear growth
                growth_multiplier = 1.0
            elif growth_rate < 100.0:
                # Quadratic-ish growth
                growth_multiplier = 0.8
            elif growth_rate < 1000.0:
                # Cubic-ish growth
                growth_multiplier = 0.6
            else:
                # Exponential or worse
                growth_multiplier = 0.3

            base_score *= growth_multiplier

        # Clamp to [0, 100]
        score = max(0.0, min(100.0, base_score))
        return round(score, 2)
