"""
Vanilla strategy - Direct problem solving without guidance.
"""

import time

from src.llm_client import LLMClient
from src.models import ExecutionResult, Problem, StrategyConfig
from src.sandbox_executor import SandboxExecutor
from src.strategy_base import StrategyBase


class VanillaStrategy(StrategyBase):
    """Vanilla strategy: direct prompting without special techniques."""

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
    ):
        """
        Initialize vanilla strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client
            sandbox: Sandbox executor
        """
        super().__init__(config, llm_client, sandbox)

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute vanilla strategy.

        Single-shot prompting: ask LLM to solve, extract code, test.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult
        """
        self.logger.info("executing_vanilla_strategy", problem_id=problem.problem_id)

        started = time.perf_counter()

        # Build prompt
        prompt = self.build_base_prompt(problem)

        # Get LLM response (errors become a terminal model_error result)
        llm_response = None
        llm_error = None
        try:
            llm_response = self.llm_client.generate(prompt)
        except Exception as e:
            llm_error = str(e)
            self.logger.error("llm_generation_failed", error=llm_error)

        # Extract code
        code = None
        if llm_response is not None:
            code = self.extract_code(llm_response.text)

        # Execute in sandbox
        sandbox_result = None
        sandbox_error = None
        success = False

        if code:
            try:
                sandbox_result = self.sandbox.execute(code, problem)
                success = sandbox_result.all_passed
            except Exception as e:
                sandbox_error = str(e)
                self.logger.error("sandbox_execution_failed", error=sandbox_error)

        # Create iteration result
        iteration_result = self.create_iteration_result(
            iteration=1,
            llm_response=llm_response,
            code=code,
            sandbox_result=sandbox_result,
            prompt=prompt,
            llm_error=llm_error,
            sandbox_error=sandbox_error,
            elapsed_seconds=time.perf_counter() - started,
        )

        # Create execution result
        execution_result = self.create_execution_result(
            problem=problem,
            iterations=[iteration_result],
            final_result=sandbox_result,
            success=success,
            execution_time_seconds=time.perf_counter() - started,
        )

        self.logger.info(
            "vanilla_strategy_completed",
            problem_id=problem.problem_id,
            success=success,
        )

        return execution_result
