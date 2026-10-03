"""Reflexion strategy: turn visible failures into bounded reflection context."""

from __future__ import annotations

import time
from typing import Literal

from src.budget import BudgetExhausted
from src.models import ExecutionResult, LLMResponse, Problem, SandboxResult
from src.strategy_base import StrategyBase
from src.utils.secrets import redact_sensitive_text


class ReflexionStrategy(StrategyBase):
    """Iteratively solve, reflect on visible failures, and avoid repeated mistakes."""

    DEFAULT_CONTEXT_CHARS = 6000

    def execute(self, problem: Problem) -> ExecutionResult:
        self.logger.info(
            "executing_reflexion_strategy",
            problem_id=problem.problem_id,
            max_iterations=self.config.max_iterations,
        )
        started = time.perf_counter()
        prompt = self.build_base_prompt(problem)
        iterations = []
        responses = []
        reflection_history: list[str] = []
        final_result = None
        success = False
        budget_stop = None
        self._reflection_budget_stop: str | None = None

        for iteration in range(1, self.config.max_iterations + 1):
            iteration_started = time.perf_counter()
            llm_response: LLMResponse | None = None
            llm_error = None
            code = None
            sandbox_result = None
            sandbox_error = None
            try:
                llm_response = self.generate(prompt)
                responses.append(llm_response)
                code = self.extract_code(llm_response.text, problem)
                if code:
                    self._before_execute(code)
                    sandbox_result = self._execute_visible_tests(code, problem)
                    if sandbox_result is None:
                        success = True
                    if sandbox_result is not None:
                        self._after_feedback(self._format_feedback(sandbox_result))
                        success = sandbox_result.all_passed
            except BudgetExhausted as exc:
                budget_stop = str(exc)
                break
            except Exception as exc:
                llm_error = str(exc) if llm_response is None else None
                sandbox_error = str(exc) if llm_response is not None else None

            iteration_result = self.create_iteration_result(
                iteration=iteration,
                llm_response=llm_response,
                code=code,
                sandbox_result=sandbox_result,
                prompt=prompt,
                llm_error=llm_error,
                sandbox_error=sandbox_error,
                elapsed_seconds=time.perf_counter() - iteration_started,
            )
            iterations.append(iteration_result)
            if sandbox_result is not None:
                final_result = sandbox_result
            if success or llm_error or sandbox_error:
                break
            if iteration >= self.config.max_iterations:
                break

            reflection_response, reflection_error = self._reflect(
                problem, code, sandbox_result, iteration, reflection_history
            )
            iteration_result.reflection_error = (
                redact_sensitive_text(reflection_error) if reflection_error else None
            )
            if reflection_response is not None:
                reflection = redact_sensitive_text(reflection_response.text.strip())
                reflection_history.append(reflection)
                iteration_result.reflection_text = reflection
                iteration_result.reflection_prompt_tokens = reflection_response.usage.prompt_tokens
                iteration_result.reflection_completion_tokens = (
                    reflection_response.usage.completion_tokens
                )
                iteration_result.reflection_usage_missing = reflection_response.usage_missing
                iteration_result.reflection_pricing_metadata = reflection_response.pricing_metadata
                if reflection_response.reasoning_text:
                    iteration_result.reflection_reasoning_text = redact_sensitive_text(
                        reflection_response.reasoning_text
                    )
            if self._reflection_budget_stop:
                budget_stop = self._reflection_budget_stop
                break
            context = self._bounded_reflection_context(reflection_history)
            prompt = self.build_reflexion_prompt(problem, code, sandbox_result, context, iteration)

        result = self.create_execution_result(
            problem=problem,
            iterations=iterations,
            final_result=final_result,
            success=success,
            llm_responses=responses,
            execution_time_seconds=time.perf_counter() - started,
        )
        if budget_stop:
            result = self.mark_budget_exhausted(result, budget_stop)
        self.logger.info(
            "reflexion_strategy_completed",
            problem_id=problem.problem_id,
            success=result.success,
            iterations=len(iterations),
        )
        return result

    def _reflect(
        self,
        problem: Problem,
        code: str | None,
        sandbox_result: SandboxResult | None,
        iteration: int,
        history: list[str],
    ) -> tuple[LLMResponse | None, str | None]:
        """Generate a reflection without allowing a reflection failure to hide the run result."""
        prompt = f"""You are reviewing attempt {iteration} for "{problem.title}".

Analyze the visible failure and explain one concrete change that should prevent
the same mistake. Do not write a replacement solution or expose hidden tests.

Code:
```python
{code or '# no code extracted'}
```

Visible test feedback:
{self._format_feedback(sandbox_result)}

Previous reflections:
{self._bounded_reflection_context(history) or '# none'}
"""
        try:
            return self.generate(prompt), None
        except BudgetExhausted as exc:
            self._reflection_budget_stop = str(exc)
            return None, None
        except Exception as exc:
            self.logger.warning("reflexion_generation_failed", error=str(exc))
            return None, str(exc)

    def _reflection_context_limit(self) -> int:
        """Return a safe character limit for persisted and prompted reflections."""
        configured = self.config.custom_params.get(
            "reflection_context_chars", self.DEFAULT_CONTEXT_CHARS
        )
        try:
            return max(1, int(configured))
        except (TypeError, ValueError):
            return self.DEFAULT_CONTEXT_CHARS

    def _bounded_reflection_context(self, history: list[str]) -> str:
        """Keep the newest reflection context within the configured prompt budget."""
        return "\n\n".join(history)[-self._reflection_context_limit() :]

    @staticmethod
    def _format_feedback(sandbox_result: SandboxResult | None) -> str:
        """Format only visible sandbox feedback for the next model call."""
        if not sandbox_result:
            return "Failed to execute: code may have syntax errors or a missing entry point"

        passed_count = sum(1 for result in sandbox_result.test_results if result.passed)
        lines = [
            f"Passed: {passed_count}/{len(sandbox_result.test_results)} tests",
            "",
        ]
        for result in sandbox_result.test_results:
            if result.passed:
                continue
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

    def _execute_visible_tests(self, code: str, problem: Problem) -> SandboxResult | None:
        """Run public and feedback cases while keeping hidden cases out of the loop."""
        visible_results = []
        if problem.public_test_cases:
            visible_results.append(self.sandbox.execute(code, problem, stage="public"))
        if problem.feedback_test_cases:
            visible_results.append(self.sandbox.execute(code, problem, stage="feedback"))
        if not visible_results:
            return None
        if len(visible_results) == 1:
            return visible_results[0]

        resource_statuses = {
            "timeout",
            "memory_error",
            "output_limit",
            "process_limit",
            "sandbox_error",
            "backend_unavailable",
        }
        status: Literal[
            "success",
            "failed",
            "timeout",
            "memory_error",
            "syntax_error",
            "runtime_error",
            "backend_unavailable",
            "output_limit",
            "process_limit",
            "sandbox_error",
            "unsupported",
        ] = (
            "success" if all(result.all_passed for result in visible_results) else "failed"
        )
        for result in visible_results:
            if result.status in resource_statuses:
                status = result.status
                break
        return SandboxResult(
            status=status,
            test_results=[
                case_result for result in visible_results for case_result in result.test_results
            ],
            execution_time=sum(result.execution_time for result in visible_results),
            all_passed=all(result.all_passed for result in visible_results),
            error_message=next(
                (result.error_message for result in visible_results if result.error_message), None
            ),
        )

    def build_reflexion_prompt(
        self,
        problem: Problem,
        previous_code: str | None,
        sandbox_result: SandboxResult | None,
        reflection: str,
        iteration: int,
    ) -> str:
        """Build the next solve prompt with a bounded reflection history."""
        return f"""We are solving "{problem.title}". This is refinement round {iteration + 1}.

Problem:
{problem.description}

Input/output mode: {problem.input_output_mode}
Entry point: {problem.entry_point}
Constraints: {problem.constraints or 'not specified'}

{self._solution_contract(problem)}

Previous code:
```python
{previous_code or '# no code extracted'}
```

Visible feedback:
{self._format_feedback(sandbox_result)}

Reflection log:
{reflection or '# no reflection was returned'}

Use the reflection to avoid repeating the error. Return only the improved Python solution in a ```python code block.
"""
