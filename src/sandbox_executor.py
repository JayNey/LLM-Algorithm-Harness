"""
Sandbox Executor - Execute code in isolated sandbox environment.
"""

import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.models import (
    Problem,
    SandboxConfig,
    SandboxResult,
    TestCase,
    TestCaseResult,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SandboxExecutor:
    """Code sandbox executor for safe code execution."""

    def __init__(self, config: SandboxConfig):
        """
        Initialize sandbox executor.

        Args:
            config: Sandbox configuration
        """
        self.config = config
        logger.info("sandbox_initialized", config=config.model_dump())

    def execute(self, code: str, problem: Problem) -> SandboxResult:
        """
        Execute code against problem test cases.

        Args:
            code: Python code to execute (must define a 'solution' function)
            problem: Problem with test cases

        Returns:
            SandboxResult with execution results

        Raises:
            ValueError: If code is invalid or missing solution function
        """
        logger.info("executing_code", problem_id=problem.problem_id, num_tests=len(problem.test_cases))

        # Validate code contains solution function
        if not self._validate_code(code):
            raise ValueError("Code must define a 'solution' function")

        # Check for disallowed imports
        self._check_imports(code)

        test_results = []
        start_time = time.time()

        for i, test_case in enumerate(problem.test_cases):
            result = self._execute_single_test(code, test_case, i)
            test_results.append(result)

        total_time = time.time() - start_time
        all_passed = all(r.passed for r in test_results)

        status = "success" if all_passed else "failed"

        sandbox_result = SandboxResult(
            status=status,
            test_results=test_results,
            execution_time=total_time,
            all_passed=all_passed,
        )

        logger.info(
            "execution_completed",
            problem_id=problem.problem_id,
            status=status,
            passed=sum(1 for r in test_results if r.passed),
            total=len(test_results),
            time=total_time,
        )

        return sandbox_result

    def _validate_code(self, code: str) -> bool:
        """
        Validate code contains required solution function.

        Args:
            code: Python code

        Returns:
            True if valid
        """
        # Check for 'def solution' pattern
        pattern = r'def\s+solution\s*\('
        return bool(re.search(pattern, code))

    def _check_imports(self, code: str) -> None:
        """
        Check for disallowed imports.

        Args:
            code: Python code

        Raises:
            ValueError: If disallowed import found
        """
        # Extract all import statements
        import_pattern = r'^\s*(?:import|from)\s+([a-zA-Z_][a-zA-Z0-9_]*)'
        imports = re.findall(import_pattern, code, re.MULTILINE)

        allowed = set(self.config.allowed_imports)

        for imp in imports:
            if imp not in allowed:
                raise ValueError(f"Disallowed import: {imp}. Allowed: {allowed}")

    def _execute_single_test(
        self, code: str, test_case: TestCase, index: int
    ) -> TestCaseResult:
        """
        Execute code against single test case.

        Args:
            code: Python code
            test_case: Test case to run
            index: Test case index

        Returns:
            TestCaseResult
        """
        try:
            start_time = time.time()

            # Execute in subprocess for isolation
            actual_output = self._run_in_subprocess(code, test_case.input)

            execution_time = time.time() - start_time

            # Check timeout
            if execution_time > self.config.timeout_seconds:
                return TestCaseResult(
                    test_case_index=index,
                    passed=False,
                    actual_output=None,
                    expected_output=test_case.expected_output,
                    error_message=f"Timeout exceeded ({execution_time:.2f}s > {self.config.timeout_seconds}s)",
                    execution_time=execution_time,
                    status="timeout",
                )

            # Compare output
            passed = self._compare_outputs(actual_output, test_case.expected_output)

            status = "passed" if passed else "wrong_answer"
            error_message = None if passed else f"Expected {test_case.expected_output}, got {actual_output}"

            return TestCaseResult(
                test_case_index=index,
                passed=passed,
                actual_output=actual_output,
                expected_output=test_case.expected_output,
                error_message=error_message,
                execution_time=execution_time,
                status=status,
            )

        except subprocess.TimeoutExpired:
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=f"Timeout: exceeded {self.config.timeout_seconds}s",
                execution_time=self.config.timeout_seconds,
                status="timeout",
            )

        except Exception as e:
            return TestCaseResult(
                test_case_index=index,
                passed=False,
                actual_output=None,
                expected_output=test_case.expected_output,
                error_message=f"Runtime error: {str(e)}",
                execution_time=time.time() - start_time,
                status="runtime_error",
            )

    def _run_in_subprocess(self, code: str, test_input: Dict[str, Any]) -> Any:
        """
        Run code in subprocess for isolation.

        Args:
            code: Python code
            test_input: Test input dictionary

        Returns:
            Function output

        Raises:
            subprocess.TimeoutExpired: If timeout exceeded
            Exception: If execution fails
        """
        # Create wrapper script
        wrapper = f"""
import sys
import json

# User code
{code}

# Execute test
if __name__ == "__main__":
    test_input = json.loads(sys.argv[1])
    result = solution(**test_input)
    print(json.dumps(result))
"""

        # Write to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(wrapper)
            temp_file = f.name

        try:
            # Run subprocess
            import json
            result = subprocess.run(
                [sys.executable, temp_file, json.dumps(test_input)],
                capture_output=True,
                text=True,
                timeout=self.config.timeout_seconds + 1,  # Add buffer
            )

            if result.returncode != 0:
                raise RuntimeError(f"Execution failed: {result.stderr}")

            # Parse output
            import json
            return json.loads(result.stdout.strip())

        finally:
            # Cleanup
            Path(temp_file).unlink(missing_ok=True)

    def _compare_outputs(self, actual: Any, expected: Any) -> bool:
        """
        Compare actual and expected outputs.

        Args:
            actual: Actual output
            expected: Expected output

        Returns:
            True if outputs match
        """
        # Handle floating point comparison
        if isinstance(actual, float) and isinstance(expected, float):
            return abs(actual - expected) < 1e-6

        # Handle lists of floats
        if isinstance(actual, list) and isinstance(expected, list):
            if len(actual) != len(expected):
                return False
            return all(
                abs(a - e) < 1e-6 if isinstance(a, float) and isinstance(e, float) else a == e
                for a, e in zip(actual, expected)
            )

        # Standard equality
        return actual == expected
