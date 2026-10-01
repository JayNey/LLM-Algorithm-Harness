"""
Main Harness - Coordinates evaluation workflow.
"""

import threading
from pathlib import Path
from typing import Any

from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    TaskID,
    TextColumn,
    TimeRemainingColumn,
)

from src.budget import BudgetedLLMClient, BudgetExhausted, BudgetTracker
from src.code_quality.analyzer import CodeQualityAnalyzer
from src.cost_alert import CostAlertManager
from src.cost_strategy import (
    CostAwareSelector,
    DifficultyBudgetMonitor,
    RunCostMonitor,
    result_cost,
)
from src.failure_classifier import classify_failure_mode
from src.llm_client import LLMClient
from src.models import (
    CostAlertConfig,
    ExecutionResult,
    HarnessConfig,
    Problem,
    SandboxResult,
    StrategyConfig,
    StrategyReport,
)
from src.problem_loader import ProblemLoader
from src.sandbox_executor import SandboxExecutor
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy
from src.strategies.reflexion import ReflexionStrategy
from src.strategies.self_consistency import SelfConsistencyStrategy
from src.strategies.vanilla import VanillaStrategy
from src.task_service import TaskService, TaskUnit
from src.utils.logging import get_logger
from src.utils.secrets import redact_sensitive_text

logger = get_logger(__name__)


class AlgorithmHarness:
    """Main harness for algorithm evaluation."""

    STRATEGY_MAP = {
        "vanilla": VanillaStrategy,
        "chain_of_thought": ChainOfThoughtStrategy,
        "multi_round_feedback": MultiRoundFeedbackStrategy,
        "self_consistency": SelfConsistencyStrategy,
        "reflexion": ReflexionStrategy,
    }

    def __init__(self, config: HarnessConfig, budget_tracker: BudgetTracker | None = None):
        """
        Initialize harness.

        Args:
            config: Harness configuration
            budget_tracker: Optional per-problem budget tracker; when present,
                every model call is gated through a budgeted client wrapper
        """
        self.config = config
        self.budget_tracker = budget_tracker
        self.cost_monitor: RunCostMonitor | None = None
        self.budget_allocation_monitor: DifficultyBudgetMonitor | None = None
        self.cost_alert_manager: CostAlertManager | None = None
        self.problem_loader = ProblemLoader()
        self.results: dict[str, list[ExecutionResult]] = {}
        self.problem_totals: dict[str, int] = {}
        self.problems_by_id: dict[str, Problem] = {}
        self.task_record = None
        self._results_lock = threading.Lock()

        # Initialize quality analyzer based on config
        if config.enable_quality_analysis:
            quality_config = config.quality_analysis_config or {}
            self.quality_analyzer = CodeQualityAnalyzer(
                enable_time=quality_config.get("enable_time_analysis", True),
                enable_space=quality_config.get("enable_space_analysis", True),
                enable_readability=quality_config.get("enable_readability_analysis", True),
                enable_style=quality_config.get("enable_style_analysis", True),
            )
            logger.info("quality_analyzer_enabled", config=quality_config)
        else:
            self.quality_analyzer = None

        logger.info("harness_initialized", config=config.redacted_dict())

    def run(
        self,
        *,
        use_task_service: bool = False,
        run_id: str | None = None,
        resume: bool = False,
    ) -> dict[str, StrategyReport]:
        """
        Run full evaluation.

        Returns:
            Dict mapping strategy name to StrategyReport
        """
        if not self.config.strategies:
            raise ValueError(
                "No strategies configured; add at least one strategy to the config"
            )
        if (
            self.config.budget_cap_usd is not None
            or self.config.cost_alerts is not None
            or self.config.budget_action is not None
        ) and not use_task_service:
            raise ValueError("Run-level cost budgets require the task service run path")
        if self.config.difficulty_strategy and not use_task_service:
            raise ValueError(
                "difficulty_strategy selection requires the task service run "
                "path; fixed-budget experiment combinations do not support it"
            )
        if use_task_service:
            return self._run_with_task_service(run_id=run_id, resume=resume)

        logger.info("harness_run_started")

        # Load problems
        problems = self._load_problems()
        self.problems_by_id = {problem.problem_id: problem for problem in problems}
        logger.info("problems_loaded", count=len(problems))

        # Run each strategy
        reports = {}
        for strategy_config in self.config.strategies:
            logger.info("running_strategy", strategy=strategy_config.name)
            report = self._run_strategy(strategy_config, problems)
            reports[strategy_config.name] = report

        logger.info("harness_run_completed", strategies=len(reports))
        return reports

    def _run_with_task_service(
        self, *, run_id: str | None = None, resume: bool = False
    ) -> dict[str, StrategyReport]:
        """Run CLI evaluations through the persistent task service."""
        problems = self._load_problems()
        self.problems_by_id = {problem.problem_id: problem for problem in problems}
        selector = self._cost_aware_selector(problems)
        budget_action = self.config.budget_action
        if self.config.budget_cap_usd is None:
            if budget_action is not None or self.config.cost_alerts is not None:
                raise ValueError("Cost alerts and budget action require budget_cap_usd")
        else:
            if budget_action is None and selector is not None:
                budget_action = "downgrade"
            if budget_action == "downgrade" and selector is None:
                raise ValueError("Budget downgrade requires a difficulty_strategy mapping")
            if budget_action is None:
                raise ValueError("Budget cap requires auto_stop or a difficulty_strategy mapping")
        monitor: RunCostMonitor | None = None
        if selector is not None or self.config.budget_cap_usd is not None:
            # The monitor exists whenever the selector runs: without a cap it
            # still records accumulated cost and unknown-usage results.
            monitor = RunCostMonitor(self.config.budget_cap_usd)
            self.cost_monitor = monitor
        allocation_monitor: DifficultyBudgetMonitor | None = None
        if self.config.budget_allocation:
            if selector is None:
                raise ValueError("Budget allocation requires a difficulty_strategy mapping")
            if budget_action == "auto_stop":
                raise ValueError("Budget allocation only supports the downgrade action")
            allocation_monitor = DifficultyBudgetMonitor(self.config.budget_allocation)
            self.budget_allocation_monitor = allocation_monitor
        service = TaskService(Path(self.config.output_dir) / "tasks")
        config_fingerprint = service.config_fingerprint(self.config)
        dataset_fingerprint = service.dataset_fingerprint(self.config.dataset_path)

        # Initialize progress tracking
        progress = Progress(
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TextColumn("•"),
            TextColumn("[green]{task.fields[success_rate]}"),
            TimeRemainingColumn(),
        )
        progress_task_id: TaskID | None = None
        progress_lock = threading.Lock()

        if resume:
            if not run_id:
                raise ValueError("--resume requires --run-id")
            record = service.get(run_id)
            if monitor is not None:
                # Same run resumed: settle already-completed problems into the
                # ledger so the remaining work cannot spend past the cap again.
                resume_problem_map = {p.problem_id: p for p in problems}
                for unit in record.units:
                    if unit.result is not None:
                        result = ExecutionResult.model_validate(unit.result)
                        monitor.add_result(result)
                        if allocation_monitor is not None:
                            difficulty = getattr(
                                resume_problem_map.get(unit.problem_id), "difficulty", None
                            )
                            allocation_monitor.add_result(result, difficulty)
        else:
            if selector is not None:
                units = []
                for problem in problems:
                    strategy_name = selector.select(problem.difficulty)
                    units.append(
                        TaskUnit(
                            unit_id=f"{strategy_name}:{problem.problem_id}:0",
                            strategy=strategy_name,
                            problem_id=problem.problem_id,
                        )
                    )
            else:
                units = [
                    TaskUnit(
                        unit_id=f"{strategy.name}:{problem.problem_id}:0",
                        strategy=strategy.name,
                        problem_id=problem.problem_id,
                    )
                    for strategy in self.config.strategies
                    for problem in problems
                ]
            if len({unit.unit_id for unit in units}) != len(units):
                raise ValueError("Duplicate strategy/problem task unit; use unique strategy names and problem IDs")
            record = service.create(
                units=units,
                config_fingerprint=config_fingerprint,
                dataset_fingerprint=dataset_fingerprint,
                run_id=run_id,
            )

        if self.config.budget_cap_usd is not None:
            self.cost_alert_manager = CostAlertManager(
                self.config.cost_alerts or CostAlertConfig(),
                record.run_id,
                service.store.root / f"{record.run_id}.cost-alerts.json",
            )
            if resume and monitor is not None:
                self._process_cost_alerts(monitor)

        problem_map = {problem.problem_id: problem for problem in problems}
        strategy_map = {strategy.name: strategy for strategy in self.config.strategies}
        try:
            runtimes = {
                name: self._prepare_strategy_runtime(strategy_config)
                for name, strategy_config in strategy_map.items()
            }
        except Exception as exc:
            service.fail(record.run_id, redact_sensitive_text(str(exc)))
            raise

        def worker(unit: TaskUnit):
            strategy_config = strategy_map[unit.strategy]
            problem = problem_map[unit.problem_id]
            strategy, sandbox = runtimes[unit.strategy]
            downgraded = False
            global_over = budget_action == "downgrade" and monitor is not None and monitor.over_cap
            difficulty_over = allocation_monitor is not None and allocation_monitor.over_cap_for(
                problem.difficulty
            )
            if global_over or difficulty_over:
                cheapest = selector.cheapest_strategy
                if cheapest != unit.strategy:
                    strategy_config = strategy_map[cheapest]
                    # Executors are stateless per SandboxConfig; only the
                    # strategy wrapper differs between runtimes, so the
                    # unit's sandbox stays valid for the hidden stage.
                    strategy, _ = runtimes[cheapest]
                    downgraded = True
                    if difficulty_over and not global_over:
                        # Difficulty-triggered downgrades log here, once per
                        # difficulty; global-triggered ones log in settle_unit.
                        if allocation_monitor.mark_trigger_logged(problem.difficulty):
                            logger.warning(
                                "difficulty_budget_reached_downgrade",
                                difficulty=problem.difficulty,
                                budget_cap_usd=float(
                                    allocation_monitor.cap_for(problem.difficulty)
                                ),
                                accumulated_cost_usd=(
                                    allocation_monitor.snapshot()
                                    .get(problem.difficulty, {})
                                    .get("accumulated_cost_usd")
                                ),
                                cheap_strategy=cheapest,
                            )
            result = self._execute_problem(strategy_config, problem, strategy, sandbox)
            if downgraded:
                result.cost_downgraded = True

            # Update progress bar
            if progress_task_id is not None:
                with progress_lock:
                    progress.advance(progress_task_id, 1)
                    # Calculate current success rate
                    completed = progress.tasks[progress_task_id].completed
                    if completed > 0:
                        # Collect results so far to calculate success rate
                        success_count = sum(
                            1 for r in self.results.get(unit.strategy, [])
                            if r.status == "success"
                        )
                        success_rate = f"{success_count}/{completed} ({success_count/completed*100:.1f}%)"
                        progress.update(progress_task_id, success_rate=success_rate)

            return result

        def settle_unit(_record: Any, unit: TaskUnit) -> None:
            # Settle only durable results. This keeps resume replay and alert
            # state aligned even if a worker finishes just before a crash.
            if monitor is None or unit.result is None:
                return
            result = ExecutionResult.model_validate(unit.result)
            monitor.add_result(result)
            if result.cost_downgraded and monitor.over_cap and monitor.record_downgrade():
                # Global-cap event only: allocation-only downgrades log (once
                # per difficulty) at the worker's decision point instead.
                logger.warning(
                    "budget_cap_reached_downgrade",
                    budget_cap_usd=self.config.budget_cap_usd,
                    accumulated_cost_usd=monitor.snapshot()["accumulated_cost_usd"],
                    cheap_strategy=selector.cheapest_strategy if selector is not None else None,
                )
            if allocation_monitor is not None:
                difficulty = getattr(problem_map.get(unit.problem_id), "difficulty", None)
                allocation_monitor.add_result(result, difficulty)
                if result.cost_downgraded:
                    # Per-difficulty count covers every downgraded problem of
                    # the difficulty, whatever triggered it; the budget-reached
                    # logs (worker for difficulty, above for global) already
                    # attributed the trigger.
                    allocation_monitor.record_downgrade(difficulty)
            self._process_cost_alerts(monitor)

        # Calculate total units for progress tracking
        if resume:
            total_units = len([u for u in record.units if u.status == "queued"])
        else:
            if selector is not None:
                total_units = len(problems)
            else:
                total_units = len(self.config.strategies) * len(problems)

        # Start progress bar
        with progress:
            progress_task_id = progress.add_task(
                "Evaluating problems...",
                total=total_units,
                success_rate="0/0 (0.0%)"
            )

            self.task_record = service.run(
                record.run_id,
                worker,
                max_workers=1 if budget_action == "auto_stop" else self.config.max_workers,
                config_fingerprint=config_fingerprint,
                dataset_fingerprint=dataset_fingerprint,
                resume=resume,
                pause_when=(
                    (lambda _: monitor.over_cap)
                    if budget_action == "auto_stop" and monitor is not None else None
                ),
                on_unit_finished=settle_unit if monitor is not None else None,
            )

        if selector is not None:
            results = self._collect_cost_aware_results(problems, selector)
            with self._results_lock:
                self.results["cost_aware"] = results
                self.problem_totals["cost_aware"] = len(problems)
            reported_ids = (
                {unit.problem_id for unit in self.task_record.units if unit.status != "queued"}
                if self.task_record.state == "paused" else {problem.problem_id for problem in problems}
            )
            report = self._generate_report(
                StrategyConfig(name="cost_aware"),
                [result for result in results if result.problem_id in reported_ids],
                [problem for problem in problems if problem.problem_id in reported_ids],
            )
            logger.info(
                "cost_aware_report_generated",
                total=len(results),
                downgraded=sum(1 for r in results if r.cost_downgraded),
            )
            return {"cost_aware": report}

        reports: dict[str, StrategyReport] = {}
        for strategy_config in self.config.strategies:
            results_by_problem = {
                unit.problem_id: self._annotate_failure_mode(
                    ExecutionResult.model_validate(unit.result), problem_map[unit.problem_id]
                )
                for unit in self.task_record.units
                if unit.strategy == strategy_config.name and unit.result is not None
            }
            results = []
            for problem in problems:
                result = results_by_problem.get(problem.problem_id)
                if result is None:
                    unit_id = f"{strategy_config.name}:{problem.problem_id}:0"
                    unit = next(item for item in self.task_record.units if item.unit_id == unit_id)
                    result = ExecutionResult(
                        problem_id=problem.problem_id,
                        strategy=strategy_config.name,
                        generated_code="",
                        evaluation_completed=False,
                        status=(
                            "cancelled"
                            if unit.status == "cancelled"
                            or (self.task_record.state == "paused" and unit.status == "queued")
                            else "error"
                        ),
                        failure_category=(
                            None if self.task_record.state == "paused" and unit.status == "queued"
                            else "system_error"
                        ),
                        difficulty=problem.difficulty,
                        error_message=unit.error or (
                            "Not run: budget cap reached"
                            if self.task_record.state == "paused" and unit.status == "queued"
                            else "Task unit did not produce a result"
                        ),
                    )
                    result = self._annotate_failure_mode(result, problem)
                results.append(result)
            with self._results_lock:
                self.results[strategy_config.name] = results
                self.problem_totals[strategy_config.name] = len(problems)
            reported_ids = (
                {
                    unit.problem_id for unit in self.task_record.units
                    if unit.strategy == strategy_config.name and unit.status != "queued"
                }
                if self.task_record.state == "paused" else {problem.problem_id for problem in problems}
            )
            reports[strategy_config.name] = self._generate_report(
                strategy_config,
                [result for result in results if result.problem_id in reported_ids],
                [problem for problem in problems if problem.problem_id in reported_ids],
            )
        return reports

    def _process_cost_alerts(self, monitor: RunCostMonitor) -> None:
        """Deliver crossed thresholds without interrupting evaluation on network failure."""
        if self.cost_alert_manager is None or self.config.budget_cap_usd is None:
            return
        snapshot = monitor.snapshot()
        try:
            events = self.cost_alert_manager.process(
                monitor.accumulated_cost,
                self.config.budget_cap_usd,
                snapshot["unknown_usage_results"],
            )
        except Exception as exc:
            # Network endpoints and credentials may be embedded in an exception
            # string; only its class is safe to include in logs.
            logger.error("cost_alert_processing_failed", error_type=type(exc).__name__)
            return
        for event in events:
            logger.warning("cost_alert", **event)

    def _cost_aware_selector(
        self, problems: list[Problem]
    ) -> CostAwareSelector | None:
        """Build the difficulty selector when configured; validate coverage."""
        mapping = self.config.difficulty_strategy
        if not mapping:
            return None
        selector = CostAwareSelector(
            mapping, allowed_strategies=list(self.STRATEGY_MAP)
        )
        selector.validate_coverage(problem.difficulty for problem in problems)
        missing = sorted(
            set(mapping.values()) - {strategy.name for strategy in self.config.strategies}
        )
        if missing:
            raise ValueError(
                "Strategies referenced by the difficulty-strategy mapping are "
                f"not configured: {', '.join(missing)}; add them to the config "
                "strategies"
            )
        return selector

    def _collect_cost_aware_results(
        self, problems: list[Problem], selector: CostAwareSelector
    ) -> list[ExecutionResult]:
        """Gather selector-mode results in dataset order, one per problem."""
        unit_by_problem = {unit.problem_id: unit for unit in self.task_record.units}
        results = []
        for problem in problems:
            unit = unit_by_problem.get(problem.problem_id)
            if unit is not None and unit.result is not None:
                results.append(self._annotate_failure_mode(
                    ExecutionResult.model_validate(unit.result),
                    self.problems_by_id[problem.problem_id],
                ))
                continue
            results.append(
                self._annotate_failure_mode(ExecutionResult(
                    problem_id=problem.problem_id,
                    strategy=selector.select(problem.difficulty),
                    generated_code="",
                    evaluation_completed=False,
                    status=(
                        "cancelled"
                        if (unit is not None and unit.status == "cancelled")
                        or (self.task_record.state == "paused" and unit is not None
                            and unit.status == "queued")
                        else "error"
                    ),
                    failure_category=(
                        None if self.task_record.state == "paused" and unit is not None
                        and unit.status == "queued" else "system_error"
                    ),
                    difficulty=problem.difficulty,
                    error_message=(unit.error if unit is not None else None)
                    or (
                        "Not run: budget cap reached"
                        if self.task_record.state == "paused" and unit is not None
                        and unit.status == "queued" else "Task unit did not produce a result"
                    ),
                    formal_evaluable=problem.formal_evaluable,
                ), problem)
            )
        return results

    def _load_problems(self) -> list[Problem]:
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
        self, strategy_config: StrategyConfig, problems: list[Problem]
    ) -> StrategyReport:
        """
        Run single strategy on all problems.

        Args:
            strategy_config: Strategy configuration
            problems: List of problems

        Returns:
            StrategyReport
        """
        strategy, sandbox = self._prepare_strategy_runtime(strategy_config)

        # Execute on all problems
        results = []
        for i, problem in enumerate(problems):
            logger.info(
                "executing_problem",
                strategy=strategy_config.name,
                problem=problem.problem_id,
                progress=f"{i+1}/{len(problems)}",
            )
            if self.budget_tracker is not None:
                self.budget_tracker.begin_problem(problem.problem_id)
            try:
                results.append(
                    self._execute_problem(strategy_config, problem, strategy, sandbox)
                )
            except BudgetExhausted as exc:
                # Budget stop is not a model or system failure: record a
                # terminal, category-free marker so the denominator stays
                # intact and the experiment report can count it as unfinished.
                redacted_reason = redact_sensitive_text(str(exc))
                logger.warning(
                    "problem_budget_exhausted",
                    strategy=strategy_config.name,
                    problem=problem.problem_id,
                    stop_reason=redacted_reason,
                )
                results.append(
                    ExecutionResult(
                        problem_id=problem.problem_id,
                        strategy=strategy_config.name,
                        generated_code="",
                        status="budget_exhausted",
                        failure_category=None,
                        difficulty=problem.difficulty,
                        error_message=redacted_reason,
                        formal_evaluable=problem.formal_evaluable,
                    )
                )
            finally:
                if self.budget_tracker is not None:
                    self.budget_tracker.finalize_problem()

        # Generate report
        report = self._generate_report(strategy_config, results, problems)

        # Store results
        self.results[strategy_config.name] = results
        self.problem_totals[strategy_config.name] = len(problems)

        return report

    def _prepare_strategy_runtime(self, strategy_config: StrategyConfig):
        """Create a strategy runtime after validating the execution backend."""
        sandbox = SandboxExecutor(self.config.sandbox_config)
        preflight_ok, preflight_detail = sandbox.health_check()
        if not preflight_ok:
            raise RuntimeError(f"Sandbox preflight failed: {preflight_detail}")
        llm_client = LLMClient(self.config.llm_config)
        if self.budget_tracker is not None:
            llm_client = BudgetedLLMClient(llm_client, self.budget_tracker)
        strategy_class = self.STRATEGY_MAP.get(strategy_config.name)
        if not strategy_class:
            raise ValueError(f"Unknown strategy: {strategy_config.name}")
        return strategy_class(strategy_config, llm_client, sandbox), sandbox

    def _execute_problem(self, strategy_config, problem, strategy, sandbox) -> ExecutionResult:
        """Execute one visible problem and its independent hidden stage."""
        if problem.unsupported_reason:
            return ExecutionResult(
                problem_id=problem.problem_id,
                strategy=strategy_config.name,
                generated_code="",
                status="unsupported",
                failure_category="unsupported",
                difficulty=problem.difficulty,
                error_message=problem.unsupported_reason,
            )

        try:
            # Strategies receive a copy with hidden cases removed. The Harness
            # retains the complete problem for the post-strategy evaluation.
            strategy_problem = problem.model_copy(update={"hidden_test_cases": []})
            result = strategy.execute(strategy_problem)
            result.formal_evaluable = problem.formal_evaluable

            # Analyze code quality if analyzer is enabled
            if self.quality_analyzer and result.generated_code:
                try:
                    quality_metrics = self.quality_analyzer.analyze(
                        result.generated_code, problem
                    )
                    result.quality_metrics = quality_metrics.model_dump()
                except Exception as e:
                    logger.warning("quality_analysis_failed", error=str(e))

            if (
                problem.formal_evaluable
                and result.generated_code
                and result.status != "budget_exhausted"
            ):
                try:
                    hidden_result = sandbox.execute(result.generated_code, problem, stage="hidden")
                except Exception as e:
                    hidden_error = redact_sensitive_text(str(e))
                    logger.error(
                        "hidden_evaluation_failed",
                        strategy=strategy_config.name,
                        problem=problem.problem_id,
                        error=hidden_error,
                    )
                    hidden_result = SandboxResult(
                        status="sandbox_error", all_passed=False, error_message=hidden_error
                    )
                result.hidden_result = hidden_result
                if not hidden_result.all_passed:
                    result.status = "failed"
                    result.failure_category = (
                        "system_error" if hidden_result.status != "failed" else "wrong_answer"
                    )
                    if not result.error_message:
                        result.error_message = "Hidden evaluation failed"
            return self._annotate_failure_mode(result, problem)
        except Exception as e:
            redacted_error = redact_sensitive_text(str(e))
            logger.error(
                "problem_execution_failed",
                strategy=strategy_config.name,
                problem=problem.problem_id,
                error=redacted_error,
            )
            return self._annotate_failure_mode(ExecutionResult(
                problem_id=problem.problem_id,
                strategy=strategy_config.name,
                generated_code="",
                status="error",
                failure_category="system_error",
                difficulty=problem.difficulty,
                error_message=redacted_error,
                formal_evaluable=problem.formal_evaluable,
            ), problem)

    @staticmethod
    def _annotate_failure_mode(result: ExecutionResult, problem: Problem) -> ExecutionResult:
        """Store a detailed, auditable mode without changing the coarse failure category."""
        if not result.evaluation_completed or result.failure_mode is not None or result.status in {
            "success", "budget_exhausted", "unsupported", "cancelled"
        }:
            return result
        try:
            decision = classify_failure_mode(
                result.model_dump(mode="python"), problem.model_dump(mode="python")
            )
        except Exception as exc:
            logger.warning("failure_mode_classification_failed", error_type=type(exc).__name__)
            result.failure_mode = "unknown"
            result.failure_mode_confidence = 0.0
            result.failure_mode_evidence = ["classifier_error"]
            return result
        if decision is not None:
            result.failure_mode = decision.mode
            result.failure_mode_confidence = decision.confidence
            result.failure_mode_evidence = list(decision.evidence)
        return result

    def _generate_report(
        self,
        strategy_config: StrategyConfig,
        results: list[ExecutionResult],
        problems: list[Problem],
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

    def _estimate_cost(self, results: list[ExecutionResult]) -> tuple[float, dict]:
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
            "unknown_usage": False,
            "unknown_pricing": False,
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
                        trace_cost = pm.get("total_cost")
                        if trace_cost is None or pm.get("usage_known") is False:
                            pricing_metadata["unknown_usage"] = True
                        else:
                            total_cost += trace_cost

                        if pm.get("pricing_known") is False or pm.get("source") == "unknown":
                            pricing_metadata["unknown_pricing"] = True

                        # Track model usage
                        model = pm.get("model", "unknown")
                        if model not in pricing_metadata["models_used"]:
                            pricing_metadata["models_used"][model] = {
                                "prompt_tokens": 0,
                                "completion_tokens": 0,
                                "total_cost": 0.0,
                                "unknown_usage": False,
                                "pricing_known": pm.get("pricing_known", True),
                                "as_of": pm.get("as_of"),
                                "prompt_price_per_1k": pm.get("prompt_price_per_1k"),
                                "completion_price_per_1k": pm.get("completion_price_per_1k"),
                            }

                        pricing_metadata["models_used"][model]["prompt_tokens"] += trace.get("prompt_tokens", 0)
                        pricing_metadata["models_used"][model]["completion_tokens"] += trace.get("completion_tokens", 0)
                        if trace_cost is not None and pm.get("usage_known") is not False:
                            pricing_metadata["models_used"][model]["total_cost"] += trace_cost
                        if trace_cost is None or pm.get("usage_known") is False:
                            pricing_metadata["models_used"][model]["unknown_usage"] = True
                    else:
                        # A trace without provider pricing cannot be treated
                        # as a free call, even when token counts are present.
                        pricing_metadata["unknown_usage"] = True
            else:
                # Token counts without pricing cannot be converted honestly;
                # leave the cost untouched and flag it as unknown instead of
                # applying a fabricated per-token default (issue #15).
                pricing_metadata["total_tokens"] += result.total_tokens
                pricing_metadata["unknown_usage"] = True

        pricing_metadata["total_cost"] = total_cost

        return total_cost, pricing_metadata

    def _calculate_by_difficulty(
        self, results: list[ExecutionResult], problems: list[Problem]
    ) -> dict[str, dict[str, Any]]:
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
                        "cost_usd": 0.0,
                    }
                by_difficulty[difficulty]["total"] += 1
                if result.status == "success":
                    by_difficulty[difficulty]["solved"] += 1
                known_cost, _ = result_cost(result)
                by_difficulty[difficulty]["cost_usd"] = round(
                    by_difficulty[difficulty]["cost_usd"] + float(known_cost), 6
                )

        # Calculate success rates
        for difficulty, stats in by_difficulty.items():
            if stats["total"] > 0:
                stats["success_rate"] = stats["solved"] / stats["total"]

        return by_difficulty

    def get_results(self, strategy_name: str) -> list[ExecutionResult]:
        """
        Get results for specific strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            List of execution results
        """
        return self.results.get(strategy_name, [])

    def get_failed_problems(self, strategy_name: str) -> list[str]:
        """
        Get problem IDs that failed for strategy.

        Args:
            strategy_name: Strategy name

        Returns:
            List of problem IDs
        """
        results = self.get_results(strategy_name)
        return [r.problem_id for r in results if r.status != "success"]

    def compare_strategies(self) -> dict:
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
