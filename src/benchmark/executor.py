"""Benchmark evaluation executor."""

from pathlib import Path
from typing import Any

from src.benchmark.suite import BenchmarkSuite
from src.harness import AlgorithmHarness
from src.models import HarnessConfig, Problem
from src.problem_loader import ProblemLoader
from src.utils.logging import get_logger

logger = get_logger(__name__)


class BenchmarkExecutor:
    """
    Execute benchmark evaluations for learning curve tracking.

    Wraps the existing AlgorithmHarness to run evaluations on
    a fixed benchmark suite.
    """

    def __init__(self, suite: BenchmarkSuite, config: HarnessConfig):
        """
        Initialize benchmark executor.

        Args:
            suite: Benchmark suite to evaluate
            config: Harness configuration
        """
        self.suite = suite
        self.config = config
        self.problem_loader = ProblemLoader()

    def execute(self) -> dict[str, Any]:
        """
        Execute benchmark evaluation on the suite.

        Returns:
            Dictionary containing evaluation results and metadata
        """
        logger.info(
            "benchmark_execution_started",
            suite=self.suite.name,
            problems=len(self.suite.problems),
        )

        # Load all problems from dataset
        all_problems = self.problem_loader.load_problems(self.config.dataset_path)
        problem_map = {p.problem_id: p for p in all_problems}

        # Filter to only problems in the benchmark suite
        benchmark_problems = []
        missing_problems = []

        for problem_id in self.suite.problems:
            if problem_id in problem_map:
                benchmark_problems.append(problem_map[problem_id])
            else:
                missing_problems.append(problem_id)
                logger.warning("benchmark_problem_not_found", problem_id=problem_id)

        if missing_problems:
            logger.warning(
                "benchmark_missing_problems",
                count=len(missing_problems),
                missing=missing_problems,
            )

        if not benchmark_problems:
            raise ValueError(
                f"No problems found in benchmark suite '{self.suite.name}'. "
                f"Ensure the problem IDs in the suite match those in the dataset."
            )

        logger.info(
            "benchmark_problems_filtered",
            total=len(self.suite.problems),
            found=len(benchmark_problems),
            missing=len(missing_problems),
        )

        # Override config to use only benchmark problems
        # We do this by temporarily modifying problem_filters
        original_filters = self.config.problem_filters
        self.config.problem_filters = {
            "limit": len(benchmark_problems),
        }

        # Create a temporary dataset with only benchmark problems
        import json
        import tempfile

        temp_dataset = tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        )
        json.dump([p.model_dump() for p in benchmark_problems], temp_dataset, indent=2)
        temp_dataset.close()

        original_dataset = self.config.dataset_path
        self.config.dataset_path = temp_dataset.name

        try:
            # Run evaluation using the harness
            harness = AlgorithmHarness(self.config)
            reports = harness.run()

            # Collect results
            results = {
                "suite": {
                    "name": self.suite.name,
                    "version": self.suite.version,
                    "frozen": self.suite.frozen,
                },
                "problems_evaluated": len(benchmark_problems),
                "problems_missing": len(missing_problems),
                "strategies": {},
            }

            for strategy_name, report in reports.items():
                results["strategies"][strategy_name] = {
                    "total": report.total,
                    "passed": report.passed,
                    "failed": report.failed,
                    "accuracy": report.accuracy,
                    "avg_time": report.avg_time,
                    "total_tokens": report.total_tokens,
                    "total_cost": report.total_cost,
                }

            logger.info(
                "benchmark_execution_completed",
                suite=self.suite.name,
                strategies=len(results["strategies"]),
            )

            return results

        finally:
            # Restore original config
            self.config.problem_filters = original_filters
            self.config.dataset_path = original_dataset

            # Clean up temp file
            Path(temp_dataset.name).unlink(missing_ok=True)
