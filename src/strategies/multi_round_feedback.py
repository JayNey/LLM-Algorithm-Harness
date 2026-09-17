"""
Multi-Round Feedback strategy - Iterative refinement with test feedback.
"""

import time
from typing import Optional

from src.llm_client import LLMClient
from src.models import ExecutionResult, Problem, SandboxResult, StrategyConfig
from src.sandbox_executor import SandboxExecutor
from src.strategy_base import StrategyBase


class MultiRoundFeedbackStrategy(StrategyBase):
    """Multi-Round Feedback: iteratively refine solution based on test results."""

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
    ):
        """
        Initialize multi-round feedback strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client
            sandbox: Sandbox executor
        """
        super().__init__(config, llm_client, sandbox)

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute multi-round feedback strategy.

        Iteratively generate code, test, provide feedback, and refine.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult
        """
        self.logger.info(
            "executing_multi_round_strategy",
            problem_id=problem.problem_id,
            max_iterations=self.config.max_iterations,
        )

        started = time.monotonic()
        iterations = []
        final_result = None
        success = False

        # Initial prompt
        prompt = self.build_base_prompt(problem)

        for iteration in range(1, self.config.max_iterations + 1):
            iteration_started = time.monotonic()
            self.logger.info("iteration_start", iteration=iteration)

            # Get LLM response (errors terminate the run but keep the trace)
            llm_response = None
            llm_error = None
            try:
                llm_response = self.llm_client.generate(prompt)
            except Exception as e:
                llm_error = str(e)
                self.logger.error(
                    "llm_generation_failed", iteration=iteration, error=llm_error
                )

            code = None
            sandbox_result = None
            sandbox_error = None

            if llm_response is not None:
                code = self.extract_code(llm_response.text)

                if code:
                    try:
                        sandbox_result = self.sandbox.execute(code, problem)
                    except Exception as e:
                        sandbox_error = str(e)
                        self.logger.error(
                            "sandbox_execution_failed", error=sandbox_error
                        )

            iteration_result = self.create_iteration_result(
                iteration=iteration,
                llm_response=llm_response,
                code=code,
                sandbox_result=sandbox_result,
                prompt=prompt,
                llm_error=llm_error,
                sandbox_error=sandbox_error,
                elapsed_seconds=time.monotonic() - iteration_started,
            )
            iterations.append(iteration_result)

            # A model failure is terminal: keep completed rounds and return
            if llm_error is not None:
                self.logger.error(
                    "multi_round_aborted_on_model_error", iteration=iteration
                )
                break

            # Keep the last valid execution regardless of pass/fail so that
            # failed runs remain inspectable
            if sandbox_result is not None:
                final_result = sandbox_result

            # Check if successful
            if sandbox_result is not None and sandbox_result.all_passed:
                success = True
                self.logger.info("solution_found", iteration=iteration)
                break

            # Prepare feedback for next iteration
            if iteration < self.config.max_iterations:
                prompt = self.build_feedback_prompt(
                    problem, code, sandbox_result, iteration
                )

        # Create execution result
        execution_result = self.create_execution_result(
            problem=problem,
            iterations=iterations,
            final_result=final_result,
            success=success,
            execution_time_seconds=time.monotonic() - started,
        )

        self.logger.info(
            "multi_round_strategy_completed",
            problem_id=problem.problem_id,
            success=success,
            iterations=len(iterations),
        )

        return execution_result

    def build_feedback_prompt(
        self,
        problem: Problem,
        previous_code: Optional[str],
        sandbox_result: Optional[SandboxResult],
        iteration: int,
    ) -> str:
        """
        Build feedback prompt for next iteration.

        Args:
            problem: Problem
            previous_code: Previous code attempt
            sandbox_result: Previous sandbox result
            iteration: Current iteration number

        Returns:
            Feedback prompt
        """
        feedback = self._format_feedback(sandbox_result)

        prompt = f"""Your previous solution for "{problem.title}" had issues.

Problem: {problem.title}

Description:
{problem.description}

{f"Constraints: {problem.constraints}" if problem.constraints else ""}

Previous Code:
```python
{previous_code if previous_code else "# No code was extracted from the previous response"}
```

Test Results:
{feedback}

Please fix the issues and provide an improved solution. Focus on:
1. Understanding why the tests failed
2. Correcting the logic errors
3. Ensuring all edge cases are handled

Provide your improved solution in a ```python code block with a 'solution' function.
"""

        return prompt

    def _format_feedback(self, sandbox_result: Optional[SandboxResult]) -> str:
        """
        Format sandbox results as feedback.

        Args:
            sandbox_result: SandboxResult

        Returns:
            Formatted feedback string
        """
        if not sandbox_result:
            return "Failed to execute: code may have syntax errors or missing 'solution' function"

        lines = []
        passed_count = sum(1 for r in sandbox_result.test_results if r.passed)
        total_count = len(sandbox_result.test_results)

        lines.append(f"Passed: {passed_count}/{total_count} tests")
        lines.append("")

        # Show failed tests
        for result in sandbox_result.test_results:
            if not result.passed:
                lines.append(f"Test {result.test_case_index + 1}: FAILED")
                lines.append(f"  Status: {result.status}")
                if result.error_message:
                    lines.append(f"  Error: {result.error_message}")
                if result.actual_output is not None:
                    lines.append(f"  Your output: {result.actual_output}")
                if result.expected_output is not None:
                    lines.append(f"  Expected: {result.expected_output}")
                lines.append("")

        return "\n".join(lines)
