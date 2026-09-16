"""
Chain of Thought (CoT) strategy - Step-by-step reasoning.
"""

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

        # Build CoT prompt
        prompt = self.build_cot_prompt(problem)

        # Get LLM response
        llm_response = self.llm_client.generate(prompt)

        # Extract code
        code = self.extract_code(llm_response.text)

        # Execute in sandbox
        sandbox_result = None
        success = False

        if code:
            try:
                sandbox_result = self.sandbox.execute(code, problem)
                success = sandbox_result.all_passed
            except Exception as e:
                self.logger.error("sandbox_execution_failed", error=str(e))

        # Create iteration result
        iteration_result = self.create_iteration_result(
            iteration=1,
            llm_response=llm_response,
            code=code,
            sandbox_result=sandbox_result,
        )

        # Create execution result
        execution_result = self.create_execution_result(
            problem=problem,
            iterations=[iteration_result],
            final_result=sandbox_result,
            success=success,
            llm_responses=[llm_response],
        )

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

        prompt = f"""Problem: {problem.title}

Description:
{problem.description}

{f"Constraints: {problem.constraints}" if problem.constraints else ""}

Test Cases:
{test_cases_str}

Please solve this problem step-by-step:

1. First, analyze the problem and identify the key requirements
2. Think through the approach and algorithm
3. Consider edge cases and constraints
4. Then provide a Python solution

Your solution should define a function named 'solution' that takes the test case inputs as parameters and returns the expected output.

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
