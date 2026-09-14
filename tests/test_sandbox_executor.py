"""
Tests for SandboxExecutor.
"""

import pytest

from src.models import Problem, SandboxConfig, TestCase
from src.sandbox_executor import SandboxExecutor


@pytest.fixture
def sandbox_config():
    """Sandbox configuration fixture."""
    return SandboxConfig(
        timeout_seconds=5,
        memory_limit_mb=256,
        allowed_imports=["math", "itertools", "collections"],
    )


@pytest.fixture
def sandbox_executor(sandbox_config):
    """SandboxExecutor fixture."""
    return SandboxExecutor(sandbox_config)


@pytest.fixture
def simple_problem():
    """Simple problem for testing."""
    return Problem(
        problem_id="test-sum",
        title="Add Two Numbers",
        description="Add two numbers",
        difficulty="easy",
        tags=["math"],
        test_cases=[
            TestCase(input={"a": 1, "b": 2}, expected_output=3),
            TestCase(input={"a": 5, "b": 7}, expected_output=12),
            TestCase(input={"a": -1, "b": 1}, expected_output=0),
        ],
    )


def test_execute_valid_code(sandbox_executor, simple_problem):
    """Test executing valid code that passes all tests."""
    code = """
def solution(a, b):
    return a + b
"""

    result = sandbox_executor.execute(code, simple_problem)

    assert result.status == "success"
    assert result.all_passed is True
    assert len(result.test_results) == 3
    assert all(r.passed for r in result.test_results)
    assert result.execution_time > 0


def test_execute_wrong_answer(sandbox_executor, simple_problem):
    """Test executing code with wrong answer."""
    code = """
def solution(a, b):
    return a - b  # Wrong: should be a + b
"""

    result = sandbox_executor.execute(code, simple_problem)

    assert result.status == "failed"
    assert result.all_passed is False
    assert result.test_results[0].passed is False
    assert result.test_results[0].status == "wrong_answer"
    assert "Expected" in result.test_results[0].error_message


def test_execute_partial_pass(sandbox_executor):
    """Test code that passes some tests but fails others."""
    problem = Problem(
        problem_id="test-partial",
        title="Partial Test",
        description="Test partial pass scenario",
        difficulty="easy",
        tags=["test"],
        test_cases=[
            TestCase(input={"x": 1}, expected_output=2),  # 1 + 1 = 2 ✓
            TestCase(input={"x": 5}, expected_output=10),  # 5 + 1 = 6 ✗
        ],
    )

    code = """
def solution(x):
    return x + 1
"""

    result = sandbox_executor.execute(code, problem)

    assert result.status == "failed"
    assert result.all_passed is False
    assert result.test_results[0].passed is True
    assert result.test_results[1].passed is False


def test_execute_runtime_error(sandbox_executor, simple_problem):
    """Test code that raises runtime error."""
    code = """
def solution(a, b):
    return a / 0  # Division by zero
"""

    result = sandbox_executor.execute(code, simple_problem)

    assert result.status == "failed"
    assert result.all_passed is False
    assert result.test_results[0].status == "runtime_error"
    assert "error" in result.test_results[0].error_message.lower()


def test_execute_timeout(sandbox_executor):
    """Test code that exceeds timeout."""
    problem = Problem(
        problem_id="test-timeout",
        title="Timeout Test",
        description="Test timeout scenario",
        difficulty="easy",
        tags=["test"],
        test_cases=[TestCase(input={"n": 1000000}, expected_output=0)],
    )

    code = """
def solution(n):
    # Simulate timeout with infinite loop
    while True:
        pass
    return 0
"""

    result = sandbox_executor.execute(code, problem)

    assert result.status == "failed"
    assert result.test_results[0].status == "timeout"
    assert "timeout" in result.test_results[0].error_message.lower()


def test_validate_code_valid(sandbox_executor):
    """Test validating valid code."""
    code = """
def solution(x):
    return x * 2
"""

    assert sandbox_executor._validate_code(code) is True


def test_validate_code_missing_solution(sandbox_executor):
    """Test validating code without solution function."""
    code = """
def helper(x):
    return x * 2
"""

    assert sandbox_executor._validate_code(code) is False


def test_validate_code_no_solution_function(sandbox_executor, simple_problem):
    """Test executing code without solution function raises ValueError."""
    code = """
def other_function(x):
    return x
"""

    with pytest.raises(ValueError, match="must define a 'solution' function"):
        sandbox_executor.execute(code, simple_problem)


def test_check_imports_allowed(sandbox_executor):
    """Test checking allowed imports."""
    code = """
import math
import collections

def solution(x):
    return math.sqrt(x)
"""

    # Should not raise
    sandbox_executor._check_imports(code)


def test_check_imports_disallowed(sandbox_executor, simple_problem):
    """Test disallowed import raises ValueError."""
    code = """
import os  # Not allowed

def solution(a, b):
    return a + b
"""

    with pytest.raises(ValueError, match="Disallowed import"):
        sandbox_executor.execute(code, simple_problem)


def test_execute_with_allowed_import(sandbox_executor):
    """Test executing code with allowed imports."""
    problem = Problem(
        problem_id="test-math",
        title="Math Test",
        description="Test math import",
        difficulty="easy",
        tags=["math"],
        test_cases=[
            TestCase(input={"x": 4}, expected_output=2.0),
            TestCase(input={"x": 9}, expected_output=3.0),
        ],
    )

    code = """
import math

def solution(x):
    return math.sqrt(x)
"""

    result = sandbox_executor.execute(code, problem)

    assert result.status == "success"
    assert result.all_passed is True


def test_compare_outputs_exact_match(sandbox_executor):
    """Test comparing exact matching outputs."""
    assert sandbox_executor._compare_outputs(42, 42) is True
    assert sandbox_executor._compare_outputs("hello", "hello") is True
    assert sandbox_executor._compare_outputs([1, 2, 3], [1, 2, 3]) is True


def test_compare_outputs_mismatch(sandbox_executor):
    """Test comparing mismatched outputs."""
    assert sandbox_executor._compare_outputs(42, 43) is False
    assert sandbox_executor._compare_outputs("hello", "world") is False
    assert sandbox_executor._compare_outputs([1, 2], [1, 2, 3]) is False


def test_compare_outputs_floats(sandbox_executor):
    """Test comparing floating point outputs with tolerance."""
    assert sandbox_executor._compare_outputs(1.0000001, 1.0) is True
    assert sandbox_executor._compare_outputs(1.1, 1.0) is False


def test_compare_outputs_float_lists(sandbox_executor):
    """Test comparing lists with floats."""
    assert sandbox_executor._compare_outputs([1.0000001, 2.0], [1.0, 2.0]) is True
    assert sandbox_executor._compare_outputs([1.1, 2.0], [1.0, 2.0]) is False


def test_execute_returns_list(sandbox_executor):
    """Test code that returns a list."""
    problem = Problem(
        problem_id="test-list",
        title="List Test",
        description="Test list return",
        difficulty="easy",
        tags=["array"],
        test_cases=[
            TestCase(input={"nums": [1, 2, 3]}, expected_output=[2, 4, 6]),
        ],
    )

    code = """
def solution(nums):
    return [x * 2 for x in nums]
"""

    result = sandbox_executor.execute(code, problem)

    assert result.status == "success"
    assert result.test_results[0].passed is True
    assert result.test_results[0].actual_output == [2, 4, 6]


def test_execute_returns_dict(sandbox_executor):
    """Test code that returns a dictionary."""
    problem = Problem(
        problem_id="test-dict",
        title="Dict Test",
        description="Test dict return",
        difficulty="easy",
        tags=["hash-table"],
        test_cases=[
            TestCase(input={"nums": [1, 2, 2, 3]}, expected_output={"1": 1, "2": 2, "3": 1}),
        ],
    )

    code = """
def solution(nums):
    freq = {}
    for num in nums:
        key = str(num)
        freq[key] = freq.get(key, 0) + 1
    return freq
"""

    result = sandbox_executor.execute(code, problem)

    assert result.status == "success"
    assert result.test_results[0].passed is True
