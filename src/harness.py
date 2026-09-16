"""
Main Harness - Coordinates evaluation workflow.
"""

from typing import Dict, List

from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    Problem,
    SandboxConfig,
    StrategyConfig,
    StrategyReport,
)
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy
from src.strategies.vanilla import VanillaStrategy
from src.utils.logging import get_logger

logger = get_logger(__name__)


class AlgorithmHarness:
    """Main harness for algorithm evaluation."""

    STRATEGY_MAP = {
        "vanilla": VanillaStrategy,
        "chain_of_thought": ChainOfThoughtStrategy,
        "multi_round_feedback": MultiRoundFeedbackStrategy,
    }

    def __init__(self, config: HarnessConfig):
        """
        Initialize harness.

        Args:
            config: Harness configuration
        """
        self.config = config
        self.problem_loader = ProblemLoader()
        self.results: Dict[str, List[ExecutionResult]] = {}
        logger.info("harness_initialized", config=config.model_dump())

    def run(self) -> Dict[str, StrategyReport]:
        """
        Run full evaluation.

        Returns:
            Dict mapping strategy name to StrategyReport
        """
        logger.info("harness_run_started")

        # Load problems
        problems = self._load_problems()
        logger.info("problems_loaded", count=len(problems))

        # Run each strategy
        reports = {}
        for strategy_config in self.config.strategies:
            logger.info("running_strategy", strategy=strategy_config.name)
            report = self._run_strategy(strategy_config, problems)
            reports[strategy_config.name] = report

        logger.info("harness_run_completed", strategies=len(reports))
        return reports

    def _load_problems(self) -> List[Problem]:
        """
        Load and filter problems.

        Returns:
            List of problems
        """
        # Load from dataset
        problems = self.problem_loader.load(self.config.dataset_path)

        # Apply filters
        if self.config.problem_filters:
            problems = self.problem_loader.filter_problems(
                problems, **self.config.problem_filters
            )
            if not problems:
                raise ValueError("No problems match the configured filters")

        return problems

    def _run_strategy(
        self, strategy_config: StrategyConfig, problems: List[Problem]
    ) -> StrategyReport:
        """
        Run single strategy on all problems.

        Args:
            strategy_config: Strategy configuration
            problems: List of problems

        Returns:
            StrategyReport
        """
        # Initialize components
        llm_client = LLMClient(self.config.llm_config)
        sandbox = SandboxExecutor(self.config.sandbox_config)

        # Get strategy class
        strategy_class = self.STRATEGY_MAP.get(strategy_config.name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_config.name}")

        # Create strategy instance
        strategy = strategy_class(strategy_config, llm_client, sandbox)

        # Execute on all problems
        results = []
        for i, problem in enumerate(problems):
            logger.info(
                "executing_problem",
                strategy=strategy_config.name,
                problem=problem.problem_id,
                progress=f"{i+1}/{len(problems)}",
            )

            try:
                result = strategy.execute(problem)
                results.append(result)
            except Exception as e:
                logger.error(
                    "problem_execution_failed",
                    strategy=strategy_config.name,
                    problem=problem.problem_id,
                    error=str(e),
                )

        # Generate report
        report = self._generate_report(strategy_config, results, problems)

        # Store results
        self.results[strategy_config.name] = results

        return report

    def _generate_report(
        self,
        strategy_config: StrategyConfig,
        results: List[ExecutionResult],
        problems: List[Problem],
    ) -> StrategyReport:
        """
        Generate strategy report.

        Args:
            strategy_config: Strategy configuration
            results: Execution results
            problems: List of problems

        Returns:
            StrategyReport
        """
        total_problems = len(problems)
        solved_problems = sum(1 for r in results if r.status == "success")
        total_attempts = sum(len(r.iterations) for r in results)
        total_tokens = sum(r.total_tokens for r in results)

        # Calculate metrics
        success_rate = solved_problems / total_problems if total_problems > 0 else 0.0
        avg_attempts = total_attempts / total_problems if total_problems > 0 else 0.0
        avg_tokens_per_problem = total_tokens / total_problems if total_problems > 0 else 0.0

        # Estimate cost (approximate)
        avg_cost_per_problem = self._estimate_cost(results) / total_problems if total_problems > 0 else 0.0

        report = StrategyReport(
            strategy_name=strategy_config.name,
            total_problems=total_problems,
            solved_problems=solved_problems,
            failed_problems=total_problems - solved_problems,
            success_rate=success_rate,
            avg_attempts_per_problem=avg_attempts,
            total_tokens=total_tokens,
            avg_tokens_per_problem=avg_tokens_per_problem,
            estimated_cost_usd=avg_cost_per_problem * total_problems,
        )

        logger.info(
            "strategy_report_generated",
            strategy=strategy_config.name,
            success_rate=success_rate,
            solved=solved_problems,
            total=total_problems,
        )

        return report

    def _estimate_cost(self, results: List[ExecutionResult]) -> float:
        """
        Estimate total cost for results.

        Args:
            results: Execution results

        Returns:
            Estimated cost in USD
        """
        # Simple approximation based on token pricing
        # This should use actual pricing from LLMClient
        total_cost = 0.0

        # Approximate: $0.002 per 1K tokens (GPT-3.5 average)
        total_tokens = sum(r.total_tokens for r in results)
        total_cost = total_tokens * (0.002 / 1000)

        return total_cost

    def get_results(self, strategy_name: str) -> List[ExecutionResult]:
        """
        Get results for specific strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            List of execution results
        """
        return self.results.get(strategy_name, [])

    def get_failed_problems(self, strategy_name: str) -> List[str]:
        """
        Get problem IDs that failed for strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            List of problem IDs
        """
        results = self.get_results(strategy_name)
        return [r.problem_id for r in results if r.status != "success"]

    def compare_strategies(self) -> Dict:
        """
        Compare all strategies.

        Returns:
            Comparison dictionary
        """
        comparison = {
            "strategies": list(self.results.keys()),
            "metrics": {},
        }

        for strategy_name, results in self.results.items():
            total = len(results)
            solved = sum(1 for r in results if r.status == "success")

            comparison["metrics"][strategy_name] = {
                "success_rate": solved / total if total > 0 else 0.0,
                "solved": solved,
                "total": total,
                "avg_tokens": sum(r.total_tokens for r in results) / total if total > 0 else 0.0,
            }

        return comparison
