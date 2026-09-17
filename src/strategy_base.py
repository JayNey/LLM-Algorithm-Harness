"""
Base strategy interface and common utilities.
"""

import re
import time
from abc import ABC, abstractmethod
from typing import List, Optional

from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    IterationResult,
    LLMResponse,
    Problem,
    SandboxResult,
    StrategyConfig,
)
from src.sandbox_executor import SandboxExecutor
from src.utils.logging import get_logger
from src.utils.secrets import redact_sensitive_data, redact_sensitive_text

logger = get_logger(__name__)


class StrategyBase(ABC):
    """Base class for all solving strategies."""

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
    ):
        """
        Initialize strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client for generation
            sandbox: Sandbox executor for testing
        """
        self.config = config
        self.llm_client = llm_client
        self.sandbox = sandbox
        self.logger = get_logger(f"{__name__}.{self.__class__.__name__}")

    @abstractmethod
    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute strategy on problem.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult
        """
        pass

    def extract_code(self, llm_response: str) -> Optional[str]:
        """
        Extract Python code from LLM response.

        Args:
            llm_response: LLM response text

        Returns:
            Extracted code or None if not found
        """
        # Look for code blocks with ```python or ```
        pattern = r'```(?:python)?\s*\n(.*?)\n```'
        matches = re.findall(pattern, llm_response, re.DOTALL)

        code = None
        if matches:
            code = matches[0].strip()
        elif "def solution(" in llm_response:
            code = llm_response.strip()
            self.logger.info("code_extracted_fallback", code_length=len(code))
        else:
            # Fallback: unclosed code block (response truncated mid-answer)
            unclosed = re.search(r'```(?:python)?\s*\n(.*)', llm_response, re.DOTALL)
            if unclosed and unclosed.group(1).strip():
                code = unclosed.group(1).strip()
                self.logger.warning("code_extracted_unclosed_block", code_length=len(code))

        if code is None:
            self.logger.warning("code_extraction_failed")
            return None

        code = self._strip_after_solution(code)
        self.logger.info("code_extracted", code_length=len(code))
        return code

    def _strip_after_solution(self, code: str) -> str:
        """
        Truncate executable statements appended after the solution function.

        Some models append their own test drivers (loops, prints, module-level
        assignments, ``if __name__`` blocks) after ``def solution``; running
        those in the sandbox causes spurious runtime errors. Definitions
        (imports, helper functions/classes, decorators) are kept because the
        solution may rely on them.
        """
        lines = code.split("\n")
        start = next(
            (i for i, line in enumerate(lines) if line.lstrip().startswith("def solution(")),
            None,
        )
        if start is None:
            return code

        end = len(lines)
        for i in range(start + 1, len(lines)):
            stripped = lines[i].lstrip()
            if stripped and not lines[i][0].isspace() and not stripped.startswith(("def ", "class ", "@")):
                end = i
                break

        truncated = "\n".join(lines[:end]).rstrip()
        if truncated != code.rstrip():
            self.logger.info(
                "code_truncated_after_solution",
                original_length=len(code),
                truncated_length=len(truncated),
            )
        return truncated

    def build_base_prompt(self, problem: Problem) -> str:
        """
        Build base problem prompt.

        Args:
            problem: Problem

        Returns:
            Formatted prompt
        """
        test_cases_str = self._format_test_cases(problem)

        prompt = f"""Problem: {problem.title}

Description:
{problem.description}

{f"Constraints: {problem.constraints}" if problem.constraints else ""}

Test Cases:
{test_cases_str}

Please provide a Python solution that defines a function named 'solution' that takes the test case inputs as parameters and returns the expected output.

Your response should include the code in a ```python code block.
"""

        return prompt

    def _format_test_cases(self, problem: Problem, limit: int = 3) -> str:
        """
        Format test cases for prompt.

        Args:
            problem: Problem
            limit: Max number of test cases to include

        Returns:
            Formatted test cases string
        """
        lines = []
        for i, tc in enumerate(problem.test_cases[:limit]):
            lines.append(f"Test {i+1}:")
            lines.append(f"  Input: {tc.input}")
            lines.append(f"  Expected Output: {tc.expected_output}")
            lines.append("")

        if len(problem.test_cases) > limit:
            lines.append(f"... and {len(problem.test_cases) - limit} more test cases")

        return "\n".join(lines)

    def create_iteration_result(
        self,
        iteration: int,
        llm_response: Optional[LLMResponse],
        code: Optional[str],
        sandbox_result: Optional[SandboxResult],
        prompt: Optional[str] = None,
        llm_error: Optional[str] = None,
        sandbox_error: Optional[str] = None,
        elapsed_seconds: float = 0.0,
    ) -> IterationResult:
        """
        Create iteration result.

        Args:
            iteration: Iteration number
            llm_response: LLM response (None when the API call failed)
            code: Extracted code
            sandbox_result: Sandbox execution result
            prompt: Request prompt sent to the model
            llm_error: Redacted model API error for this iteration
            sandbox_error: Redacted sandbox failure reason for this iteration
            elapsed_seconds: Wall-clock duration of this iteration

        Returns:
            IterationResult
        """
        return IterationResult(
            iteration=iteration,
            prompt_tokens=llm_response.usage.prompt_tokens if llm_response else 0,
            completion_tokens=llm_response.usage.completion_tokens if llm_response else 0,
            code_extracted=code,
            sandbox_result=sandbox_result,
            prompt=redact_sensitive_text(prompt) if prompt else None,
            response_text=redact_sensitive_text(llm_response.text) if llm_response else None,
            llm_error=redact_sensitive_text(llm_error) if llm_error else None,
            sandbox_error=redact_sensitive_text(sandbox_error) if sandbox_error else None,
            usage_missing=llm_response.usage_missing if llm_response else False,
            elapsed_seconds=max(elapsed_seconds, 0.0),
        )

    def _derive_failure_category(
        self,
        iterations: list,
        final_result: Optional[SandboxResult],
        success: bool,
    ) -> Optional[str]:
        """
        Classify why an unsuccessful execution failed.

        Precedence: the latest terminal reason wins — model API failure,
        sandbox/system failure, a final round that produced no code, and
        only then the program answering incorrectly.
        """
        if success:
            return None
        for iteration in reversed(iterations):
            if iteration.llm_error:
                return "model_error"
        if iterations:
            last = iterations[-1]
            if last.sandbox_error:
                return "system_error"
            if last.code_extracted is None and last.sandbox_result is None:
                return "code_extraction_failed"
        if final_result is not None:
            return "wrong_answer"
        return "code_extraction_failed"

    def _build_llm_traces(self, iterations: list) -> list:
        """
        Build redacted per-round traces from iteration results.
        """
        traces = []
        for it in iterations:
            trace = {
                "iteration": it.iteration,
                "prompt": it.prompt,
                "response_text": it.response_text,
                "code_extracted": it.code_extracted,
                "llm_error": it.llm_error,
                "sandbox_error": it.sandbox_error,
                "prompt_tokens": it.prompt_tokens,
                "completion_tokens": it.completion_tokens,
                "usage_missing": it.usage_missing,
                "elapsed_seconds": it.elapsed_seconds,
                "sandbox": it.sandbox_result.model_dump() if it.sandbox_result else None,
            }
            traces.append(redact_sensitive_data(trace))
        return traces

    def create_execution_result(
        self,
        problem: Problem,
        iterations: list,
        final_result: Optional[SandboxResult],
        success: bool,
        llm_responses: Optional[List[LLMResponse]] = None,
        failure_category: Optional[str] = None,
        execution_time_seconds: Optional[float] = None,
    ) -> ExecutionResult:
        """
        Create final execution result.

        Args:
            problem: Problem
            iterations: List of iteration results
            final_result: Last valid sandbox result (kept on failure too)
            success: Whether solution succeeded
            llm_responses: Optional list of LLM responses for tracing
            failure_category: Explicit category; derived when omitted
            execution_time_seconds: Measured duration; callers should always
                pass a real measurement

        Returns:
            ExecutionResult
        """
        total_prompt_tokens = sum(it.prompt_tokens for it in iterations)
        total_completion_tokens = sum(it.completion_tokens for it in iterations)

        # Extract generated code from the last iteration
        generated_code = iterations[-1].code_extracted if iterations and iterations[-1].code_extracted else ""

        # Determine status
        status = "success" if success else ("error" if final_result and final_result.error_message else "failed")

        # Extract test results
        test_results = final_result.test_results if final_result else []

        # Extract error message
        error_message = final_result.error_message if final_result else None

        # Build LLM traces with pricing metadata
        llm_traces = []
        if llm_responses:
            for idx, response in enumerate(llm_responses):
                trace = {
                    "iteration": idx + 1,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
                if response.pricing_metadata:
                    trace["pricing_metadata"] = response.pricing_metadata
                llm_traces.append(trace)

        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=self.config.name,
            generated_code=generated_code,
            status=status,
            failure_category=(
                failure_category
                if failure_category is not None
                else self._derive_failure_category(iterations, final_result, success)
            ),
            difficulty=problem.difficulty,
            iterations=iterations,
            final_result=final_result,
            test_results=test_results,
            error_message=error_message,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            execution_time_seconds=(
                execution_time_seconds if execution_time_seconds is not None else 0.0
            ),
            llm_traces=llm_traces if llm_responses else self._build_llm_traces(iterations),
        )
