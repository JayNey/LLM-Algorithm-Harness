"""
Main Harness - Coordinates evaluation workflow.
"""

from typing import Any, Dict, List

from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    HarnessConfig,
    LLMConfig,
    Problem,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
    StrategyReport,
)
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy
from src.strategies.vanilla import VanillaStrategy
from src.utils.logging import get_logger
from src.utils.secrets import redact_sensitive_text

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
        self.problem_totals: Dict[str, int] = {}
        logger.info("harness_initialized", config=config.redacted_dict())

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

            if problem.unsupported_reason:
                results.append(
                    ExecutionResult(
                        problem_id=problem.problem_id,
                        strategy=strategy_config.name,
                        generated_code="",
                        status="unsupported",
                        failure_category="unsupported",
                        difficulty=problem.difficulty,
                        error_message=problem.unsupported_reason,
                    )
                )
                continue

            try:
                # Strategies receive a copy with hidden cases removed. The
                # Harness retains the complete problem for the post-strategy
                # evaluation below, so custom strategies cannot inspect or run
                # hidden cases during candidate generation.
                strategy_problem = problem.model_copy(update={"hidden_test_cases": []})
                result = strategy.execute(strategy_problem)
                result.formal_evaluable = problem.formal_evaluable
                if (
                    problem.formal_evaluable
                    and result.generated_code
                    and not problem.unsupported_reason
                ):
                    try:
                        hidden_result = sandbox.execute(
                            result.generated_code, problem, stage="hidden"
                        )
                    except Exception as e:
                        hidden_error = redact_sensitive_text(str(e))
                        logger.error(
                            "hidden_evaluation_failed",
                            strategy=strategy_config.name,
                            problem=problem.problem_id,
                            error=hidden_error,
                        )
                        hidden_result = SandboxResult(
                            status="sandbox_error",
                            all_passed=False,
                            error_message=hidden_error,
                        )
                    result.hidden_result = hidden_result
                    if not hidden_result.all_passed:
                        result.status = "failed"
                        result.failure_category = (
                            "system_error"
                            if hidden_result.status != "failed"
                            else "wrong_answer"
                        )
                        # Preserve original error_message if present
                        if not result.error_message:
                            result.error_message = "Hidden evaluation failed"
                results.append(result)
            except Exception as e:
                # Every problem x strategy combination must end up with a
                # terminal record, even when the strategy itself crashes
                redacted_error = redact_sensitive_text(str(e))
                logger.error(
                    "problem_execution_failed",
                    strategy=strategy_config.name,
                    problem=problem.problem_id,
                    error=redacted_error,
                )
                results.append(
                    ExecutionResult(
                        problem_id=problem.problem_id,
                        strategy=strategy_config.name,
                        generated_code="",
                        status="error",
                        failure_category="system_error",
                        difficulty=problem.difficulty,
                        error_message=redacted_error,
                        formal_evaluable=problem.formal_evaluable,
                    )
                )

        # Generate report
        report = self._generate_report(strategy_config, results, problems)

        # Store results
        self.results[strategy_config.name] = results
        self.problem_totals[strategy_config.name] = len(problems)

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
        model_failed = sum(1 for r in results if r.failure_category == "model_error")
        system_failed = sum(1 for r in results if r.failure_category == "system_error")
        total_attempts = sum(len(r.iterations) for r in results)
        total_tokens = sum(r.total_tokens for r in results)

        # Calculate metrics
        success_rate = solved_problems / total_problems if total_problems > 0 else 0.0
        avg_attempts = total_attempts / total_problems if total_problems > 0 else 0.0
        avg_tokens_per_problem = total_tokens / total_problems if total_problems > 0 else 0.0

        # Estimate cost with pricing metadata
        total_cost, pricing_metadata = self._estimate_cost(results)

        # Calculate by_difficulty breakdown
        by_difficulty = self._calculate_by_difficulty(results, problems)
        formal_evaluable = sum(1 for problem in problems if problem.formal_evaluable)
        formal_solved = sum(
            1
            for problem, result in zip(problems, results, strict=False)
            if (
                problem.formal_evaluable
                and result.formal_evaluable
                and result.hidden_result is not None
                and result.hidden_result.all_passed
            )
        )

        report = StrategyReport(
            strategy_name=strategy_config.name,
            total_problems=total_problems,
            solved_problems=solved_problems,
            failed_problems=total_problems - solved_problems,
            success_rate=success_rate,
            avg_attempts_per_problem=avg_attempts,
            total_tokens=total_tokens,
            avg_tokens_per_problem=avg_tokens_per_problem,
            estimated_cost_usd=total_cost,
            pricing_metadata=pricing_metadata,
            by_difficulty=by_difficulty,
            model_failed_problems=model_failed,
            system_failed_problems=system_failed,
            formal_evaluable_problems=formal_evaluable,
            sample_only_problems=total_problems - formal_evaluable,
            formal_solved_problems=formal_solved,
            formal_success_rate=(formal_solved / formal_evaluable if formal_evaluable else 0.0),
        )

        logger.info(
            "strategy_report_generated",
            strategy=strategy_config.name,
            success_rate=success_rate,
            solved=solved_problems,
            total=total_problems,
        )

        return report

    def _estimate_cost(self, results: List[ExecutionResult]) -> tuple[float, dict]:
        """
        Estimate total cost for results using actual pricing metadata.

        Args:
            results: Execution results

        Returns:
            Tuple of (total_cost_usd, pricing_metadata_dict)
        """
        total_cost = 0.0
        pricing_metadata = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "models_used": {},
            "has_actual_pricing": False,
        }

        for result in results:
            if result.llm_traces:
                # Use actual pricing from llm_traces
                for trace in result.llm_traces:
                    pricing_metadata["total_prompt_tokens"] += trace.get("prompt_tokens", 0)
                    pricing_metadata["total_completion_tokens"] += trace.get("completion_tokens", 0)
                    pricing_metadata["total_tokens"] += trace.get("total_tokens", 0)

                    if "pricing_metadata" in trace:
                        pricing_metadata["has_actual_pricing"] = True
                        pm = trace["pricing_metadata"]

                        # Accumulate cost
                        total_cost += pm.get("total_cost", 0.0)

                        # Track model usage
                        model = pm.get("model", "unknown")
                        if model not in pricing_metadata["models_used"]:
                            pricing_metadata["models_used"][model] = {
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_cost": 0.0,
                                "prompt_price_per_1k": pm.get("prompt_price_per_1k"),
                                "completion_price_per_1k": pm.get("completion_price_per_1k"),
                            }

                        pricing_metadata["models_used"][model]["prompt_tokens"] += trace.get("prompt_tokens", 0)
                        pricing_metadata["models_used"][model]["completion_tokens"] += trace.get("completion_tokens", 0)
                        pricing_metadata["models_used"][model]["total_cost"] += pm.get("total_cost", 0.0)
            else:
                # Fallback: use token counts without pricing
                pricing_metadata["total_tokens"] += result.total_tokens
                # Approximate: $0.002 per 1K tokens (fallback default)
                total_cost += result.total_tokens * (0.002 / 1000)

        pricing_metadata["total_cost"] = total_cost

        return total_cost, pricing_metadata

    def _calculate_by_difficulty(
        self, results: List[ExecutionResult], problems: List[Problem]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Calculate success rate breakdown by difficulty level.

        Args:
            results: Execution results
            problems: List of problems

        Returns:
            Dictionary mapping difficulty level to stats
        """
        # Group results by difficulty (use result.difficulty directly if available)
        by_difficulty = {}
        for result in results:
            # Prefer result.difficulty (populated in newer runs)
            difficulty = result.difficulty
            if not difficulty:
                # Fallback: look up from problems list (for backward compatibility)
                problem_map = {p.problem_id: p.difficulty for p in problems}
                difficulty = problem_map.get(result.problem_id)

            if difficulty:
                if difficulty not in by_difficulty:
                    by_difficulty[difficulty] = {
                        "solved": 0,
                        "total": 0,
                        "success_rate": 0.0,
                    }
                by_difficulty[difficulty]["total"] += 1
                if result.status == "success":
                    by_difficulty[difficulty]["solved"] += 1

        # Calculate success rates
        for difficulty, stats in by_difficulty.items():
            if stats["total"] > 0:
                stats["success_rate"] = stats["solved"] / stats["total"]

        return by_difficulty

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
            # Use the same denominator as the strategy report so that a
            # problem dropped mid-run still counts against the strategy
            total = self.problem_totals.get(strategy_name, len(results))
            solved = sum(1 for r in results if r.status == "success")

            comparison["metrics"][strategy_name] = {
                "success_rate": solved / total if total > 0 else 0.0,
                "solved": solved,
                "total": total,
                "avg_tokens": sum(r.total_tokens for r in results) / total if total > 0 else 0.0,
            }

        return comparison
