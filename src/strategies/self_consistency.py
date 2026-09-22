"""
Self-Consistency Strategy Implementation.

Generates multiple candidate solutions with high temperature and selects
the most frequent correct answer through voting.
"""

import time
from collections import Counter
from typing import Dict, List, Optional

from src.models import (
    ExecutionResult,
    IterationResult,
    LLMResponse,
    Problem,
    SandboxResult,
)
from src.strategy_base import StrategyBase
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SelfConsistencyStrategy(StrategyBase):
    """
    Self-Consistency strategy that generates multiple candidate solutions
    and selects the best answer through voting.
    """

    def __init__(self, *args, **kwargs):
        """Initialize Self-Consistency strategy with configurable candidate count."""
        super().__init__(*args, **kwargs)
        # Get num_candidates from custom_params, default to 5
        num_candidates = self.config.custom_params.get("num_candidates", 5)

        # Validate num_candidates
        if not isinstance(num_candidates, int) or num_candidates < 1:
            self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
            self.logger.warning(
                "invalid_num_candidates",
                provided_value=num_candidates,
                using_default=5,
            )
            self.num_candidates = 5
        else:
            self.num_candidates = num_candidates

        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")
        self.logger.info(
            "self_consistency_initialized",
            num_candidates=self.num_candidates,
        )

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute Self-Consistency strategy on the given problem.

        Generates N candidate solutions with high temperature, tests each one,
        and selects the most frequent correct answer through voting.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult with all candidate iterations and voting statistics
        """
        start_time = time.time()
        iterations: List[IterationResult] = []
        llm_responses: List[Optional[LLMResponse]] = []

        # Step 1: Generate N candidate solutions
        self.logger.info(
            "generating_candidates",
            problem_id=problem.problem_id,
            num_candidates=self.num_candidates,
        )

        base_prompt = self.build_base_prompt(problem)

        for i in range(self.num_candidates):
            iter_start = time.time()
            iteration_num = i + 1

            try:
                # Generate with high temperature (0.8) for diversity
                llm_response = self.llm_client.generate(
                    base_prompt,
                    system_prompt=self.config.system_prompt,
                    temperature=0.8,  # High temperature for diversity
                    max_tokens=(
                        self.config.max_tokens
                        if "max_tokens" in self.config.model_fields_set
                        else None
                    ),
                    custom_params=self.config.custom_params,
                )
                llm_responses.append(llm_response)

                # Extract code from response
                code = self.extract_code(llm_response.text, problem)

                # Test the candidate solution
                sandbox_result = None
                sandbox_error = None
                if code:
                    try:
                        sandbox_result = self.sandbox.execute(problem, code)
                    except Exception as e:
                        sandbox_error = str(e)
                        self.logger.warning(
                            "sandbox_execution_failed",
                            iteration=iteration_num,
                            error=sandbox_error,
                        )

                # Record iteration result
                iter_elapsed = time.time() - iter_start
                iteration_result = self.create_iteration_result(
                    iteration=iteration_num,
                    llm_response=llm_response,
                    code=code,
                    sandbox_result=sandbox_result,
                    prompt=base_prompt,
                    sandbox_error=sandbox_error,
                    elapsed_seconds=iter_elapsed,
                )
                iterations.append(iteration_result)

                self.logger.info(
                    "candidate_generated",
                    iteration=iteration_num,
                    code_extracted=code is not None,
                    tests_passed=sandbox_result.all_passed if sandbox_result else False,
                )

            except Exception as e:
                # Handle LLM API errors
                llm_error = str(e)
                llm_responses.append(None)
                iter_elapsed = time.time() - iter_start

                iteration_result = self.create_iteration_result(
                    iteration=iteration_num,
                    llm_response=None,
                    code=None,
                    sandbox_result=None,
                    prompt=base_prompt,
                    llm_error=llm_error,
                    elapsed_seconds=iter_elapsed,
                )
                iterations.append(iteration_result)

                self.logger.error(
                    "candidate_generation_failed",
                    iteration=iteration_num,
                    error=llm_error,
                )

        # Step 2: Vote on successful candidates
        execution_time = time.time() - start_time
        voting_result = self._vote_on_candidates(iterations)

        # Step 3: Create final execution result
        final_result = voting_result["final_sandbox_result"]
        success = voting_result["success"]

        execution_result = self.create_execution_result(
            problem=problem,
            iterations=iterations,
            final_result=final_result,
            success=success,
            llm_responses=llm_responses,
            execution_time_seconds=execution_time,
        )

        # Add voting statistics as metadata
        voting_metadata = {
            "voting_statistics": voting_result["voting_stats"],
            "selected_code_frequency": voting_result["selected_frequency"],
            "total_candidates": self.num_candidates,
            "passing_candidates": voting_result["passing_count"],
        }

        # Add failure analysis if there are failed candidates
        if voting_result["passing_count"] < self.num_candidates:
            failure_analysis = self._analyze_failures(iterations)
            voting_metadata["failure_analysis"] = failure_analysis

        execution_result.llm_traces.append(voting_metadata)

        self.logger.info(
            "self_consistency_completed",
            problem_id=problem.problem_id,
            success=success,
            passing_candidates=voting_result["passing_count"],
            selected_frequency=voting_result["selected_frequency"],
        )

        return execution_result

    def _vote_on_candidates(self, iterations: List[IterationResult]) -> Dict:
        """
        Vote on passing candidate solutions and select the most frequent one.

        When all candidates fail, returns the first candidate's result as a fallback
        to preserve error information for debugging.

        Args:
            iterations: List of iteration results

        Returns:
            Dictionary with voting results and final sandbox result
        """
        # Collect passing candidates
        passing_candidates = []
        for iteration in iterations:
            if (
                iteration.code_extracted
                and iteration.sandbox_result
                and iteration.sandbox_result.all_passed
            ):
                passing_candidates.append(
                    {
                        "code": iteration.code_extracted,
                        "sandbox_result": iteration.sandbox_result,
                        "iteration": iteration.iteration,
                    }
                )

        self.logger.info(
            "voting_on_candidates",
            total_candidates=len(iterations),
            passing_candidates=len(passing_candidates),
        )

        # Case 1: No passing candidates - all failed
        if not passing_candidates:
            return {
                "success": False,
                "final_sandbox_result": (iterations[-1].sandbox_result if iterations else None),
                "voting_stats": {},
                "selected_frequency": 0,
                "passing_count": 0,
            }

        # Case 2: Vote on passing candidates by code string
        code_counts = Counter(candidate["code"] for candidate in passing_candidates)
        most_common_code, frequency = code_counts.most_common(1)[0]

        # Find the sandbox result for the selected code
        selected_candidate = next(c for c in passing_candidates if c["code"] == most_common_code)

        # Build voting statistics as list of dicts for easier reporting
        voting_stats = [{"code": code, "count": count} for code, count in code_counts.most_common()]

        self.logger.info(
            "voting_completed",
            selected_code_frequency=frequency,
            unique_passing_codes=len(code_counts),
            total_passing=len(passing_candidates),
        )

        return {
            "success": True,
            "final_sandbox_result": selected_candidate["sandbox_result"],
            "voting_stats": voting_stats,
            "selected_frequency": frequency,
            "passing_count": len(passing_candidates),
        }

    def _analyze_failures(self, iterations: List[IterationResult]) -> Dict:
        """
        Analyze failed candidates to identify common failure patterns.

        Args:
            iterations: List of iteration results

        Returns:
            Dictionary with failure analysis statistics
        """
        failures = {
            "no_code_extracted": 0,
            "sandbox_errors": 0,
            "test_failures": 0,
            "llm_errors": 0,
        }

        failure_reasons = []

        for iteration in iterations:
            # LLM generation failed
            if iteration.llm_error:
                failures["llm_errors"] += 1
                failure_reasons.append(
                    {
                        "iteration": iteration.iteration,
                        "type": "llm_error",
                        "reason": iteration.llm_error[:100],  # Truncate long errors
                    }
                )
                continue

            # Code extraction failed
            if not iteration.code_extracted:
                failures["no_code_extracted"] += 1
                failure_reasons.append(
                    {
                        "iteration": iteration.iteration,
                        "type": "no_code_extracted",
                        "reason": "Failed to extract valid code from LLM response",
                    }
                )
                continue

            # Sandbox execution error
            if iteration.sandbox_error:
                failures["sandbox_errors"] += 1
                failure_reasons.append(
                    {
                        "iteration": iteration.iteration,
                        "type": "sandbox_error",
                        "reason": iteration.sandbox_error[:100],  # Truncate long errors
                    }
                )
                continue

            # Test failure
            if iteration.sandbox_result and not iteration.sandbox_result.all_passed:
                failures["test_failures"] += 1
                failed_tests = sum(
                    1 for tr in iteration.sandbox_result.test_results if not tr.passed
                )
                failure_reasons.append(
                    {
                        "iteration": iteration.iteration,
                        "type": "test_failure",
                        "reason": f"{failed_tests} test(s) failed",
                    }
                )

        return {
            "summary": failures,
            "details": failure_reasons,
            "total_failures": sum(failures.values()),
        }
