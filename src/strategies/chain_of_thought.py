"""
Chain of Thought (CoT) strategy - Step-by-step reasoning.
"""

import time

from src.budget import BudgetExhausted
from src.llm_client import LLMClient
from src.models import ExecutionResult, Problem, StrategyConfig
from src.sandbox_executor import SandboxExecutor
from src.strategy_base import StrategyBase


class ChainOfThoughtStrategy(StrategyBase):
    """Chain of Thought strategy: prompt LLM to reason step-by-step."""

    def __init__(
        self,
        config: StrategyConfig,
        llm_client: LLMClient,
        sandbox: SandboxExecutor,
    ):
        """
        Initialize CoT strategy.

        Args:
            config: Strategy configuration
            llm_client: LLM client
            sandbox: Sandbox executor
        """
        super().__init__(config, llm_client, sandbox)

    def execute(self, problem: Problem) -> ExecutionResult:
        """
        Execute Chain of Thought strategy.

        Prompts LLM to think step-by-step before coding.

        Args:
            problem: Problem to solve

        Returns:
            ExecutionResult
        """
        self.logger.info("executing_cot_strategy", problem_id=problem.problem_id)

        started = time.perf_counter()

        # Build CoT prompt
        prompt = self.build_cot_prompt(problem)

        # Get LLM response (errors become a terminal model_error result)
        llm_response = None
        llm_error = None
        budget_stop = None
        try:
            llm_response = self.generate(prompt)
        except BudgetExhausted as e:
            budget_stop = str(e)
            self.logger.warning("llm_generation_stopped_on_budget", stop_reason=budget_stop)
        except Exception as e:
            llm_error = str(e)
            self.logger.error("llm_generation_failed", error=llm_error)

        # Extract code
        code = None
        if llm_response is not None:
            code = self.extract_code(llm_response.text, problem)

        # Execute in sandbox
        sandbox_result = None
        sandbox_error = None
        success = False

        if code:
            try:
                # Trigger debug hook before execution
                self._before_execute(code)

                if problem.public_test_cases:
                    sandbox_result = self.sandbox.execute(code, problem, stage="public")
                    success = sandbox_result.all_passed
                elif problem.feedback_test_cases:
                    # A feedback-only problem still has an executable visible stage.
                    sandbox_result = self.sandbox.execute(code, problem, stage="feedback")
                    success = sandbox_result.all_passed
                else:
                    # Hidden-only problems are finalized by Harness after this strategy.
                    success = True

                # Trigger debug hook after feedback is available
                if sandbox_result:
                    feedback = f"All passed: {sandbox_result.all_passed}, Status: {sandbox_result.status}"
                    if sandbox_result.error_message:
                        feedback += f", Error: {sandbox_result.error_message}"
                    self._after_feedback(feedback)
            except Exception as e:
                sandbox_error = str(e)
                self.logger.error("sandbox_execution_failed", error=sandbox_error)
                self._after_feedback(f"Sandbox error: {sandbox_error}")

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
            llm_responses=[llm_response],
            execution_time_seconds=time.perf_counter() - started,
        )

        if budget_stop is not None:
            execution_result = self.mark_budget_exhausted(execution_result, budget_stop)

        self.logger.info(
            "cot_strategy_completed",
            problem_id=problem.problem_id,
            success=success,
        )

        return execution_result

    def build_cot_prompt(self, problem: Problem) -> str:
        """
        Build Chain of Thought prompt.

        Args:
            problem: Problem

        Returns:
            CoT prompt with reasoning instructions
        """
        test_cases_str = self._format_test_cases(problem)
        contract = self._solution_contract(problem)

        prompt = f"""Problem: {problem.title}

Description:
{problem.description}

Input/Output Mode: {problem.input_output_mode}
Entry Point: {problem.entry_point}
Judge: {problem.judge_config.comparison}, float tolerance={problem.judge_config.float_tolerance}, whitespace={problem.judge_config.whitespace}

{f"Constraints: {problem.constraints}" if problem.constraints else ""}

Test Cases:
{test_cases_str}

Please solve this problem step-by-step:

1. First, analyze the problem and identify the key requirements
2. Think through the approach and algorithm
3. Consider edge cases and constraints
4. Then provide a Python solution

{contract}

Please structure your response as:

**Analysis:**
[Your analysis here]

**Approach:**
[Your approach here]

**Solution:**
```python
[Your code here]
```
"""

        return prompt
