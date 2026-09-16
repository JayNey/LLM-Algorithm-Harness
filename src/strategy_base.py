"""
Base strategy interface and common utilities.
"""

import re
from abc import ABC, abstractmethod
from typing import Optional

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
        llm_response: LLMResponse,
        code: Optional[str],
        sandbox_result: Optional[SandboxResult],
    ) -> IterationResult:
        """
        Create iteration result.

        Args:
            iteration: Iteration number
            llm_response: LLM response
            code: Extracted code
            sandbox_result: Sandbox execution result

        Returns:
            IterationResult
        """
        return IterationResult(
            iteration=iteration,
            prompt_tokens=llm_response.usage.prompt_tokens,
            completion_tokens=llm_response.usage.completion_tokens,
            code_extracted=code,
            sandbox_result=sandbox_result,
        )

    def create_execution_result(
        self,
        problem: Problem,
        iterations: list,
        final_result: Optional[SandboxResult],
        success: bool,
    ) -> ExecutionResult:
        """
        Create final execution result.

        Args:
            problem: Problem
            iterations: List of iteration results
            final_result: Final sandbox result
            success: Whether solution succeeded

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

        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=self.config.name,
            generated_code=generated_code,
            status=status,
            iterations=iterations,
            final_result=final_result,
            test_results=test_results,
            error_message=error_message,
            total_tokens=total_prompt_tokens + total_completion_tokens,
            execution_time_seconds=0.0,  # Will be set by caller if needed
        )
