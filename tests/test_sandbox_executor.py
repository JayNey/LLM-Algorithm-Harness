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
        backend="host",
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


def test_function_mode_keeps_debug_stdout_separate(sandbox_executor):
    """Debug prints do not corrupt the function result channel."""
    problem = Problem(
        problem_id="debug-output",
        title="Debug Output",
        description="A function problem whose solution prints debug information.",
        difficulty="easy",
        test_cases=[{"input": {"value": 2}, "expected_output": 4}],
    )

    result = sandbox_executor.execute(
        "def solution(value):\n    print('debug line')\n    return value * 2",
        problem,
    )

    assert result.status == "success"
    assert result.test_results[0].actual_output == 4


def test_function_result_channel_uses_trusted_serializer(sandbox_config):
    """Candidate monkeypatches cannot replace the wrapper's result serializer."""
    problem = Problem(
        problem_id="serializer-isolation",
        title="Serializer Isolation",
        description="A function problem used to verify result-channel isolation.",
        difficulty="easy",
        test_cases=[{"input": {}, "expected_output": 1}],
    )

    result = SandboxExecutor(
        sandbox_config.model_copy(update={"allowed_imports": ["json"]})
    ).execute(
        "import json\n"
        "json.dumps = lambda value: '0'\n"
        "def solution():\n"
        "    return 1",
        problem,
    )

    assert result.status == "success"
    assert result.test_results[0].actual_output == 1


def test_stdin_stdout_problem_executes_without_solution_function(sandbox_config):
    """stdin/stdout programs receive raw input and their text output is judged."""
    problem = Problem(
        problem_id="stdin-add",
        title="Standard Input Add",
        description="Read two integers from standard input and print their sum.",
        difficulty="easy",
        input_output_mode="stdin_stdout",
        entry_point="main()",
        public_test_cases=[{"input": "2 3\n", "expected_output": "5\n"}],
    )
    executor = SandboxExecutor(sandbox_config)

    result = executor.execute(
        "a, b = map(int, input().split())\nprint(a + b)",
        problem,
    )

    assert result.status == "success"
    assert result.test_results[0].actual_output == "5\n"


def test_stdin_stdout_tokens_whitespace_policy(sandbox_config):
    """Token comparison makes internal whitespace rules explicit."""
    problem = Problem(
        problem_id="stdin-whitespace",
        title="Whitespace Policy",
        description="A stdin/stdout problem with token-based output comparison.",
        difficulty="easy",
        input_output_mode="stdin_stdout",
        entry_point="main()",
        judge_config={"whitespace": "tokens"},
        public_test_cases=[{"input": "", "expected_output": "1 2\n"}],
    )

    result = SandboxExecutor(sandbox_config).execute(
        "print('1   2')",
        problem,
    )

    assert result.status == "success"


def test_stdin_stdout_json_parse_errors_are_not_model_wrong_answers(sandbox_config):
    """Malformed JSON stdout is reported as a protocol/runtime failure."""
    problem = Problem(
        problem_id="stdin-json-error",
        title="Malformed JSON",
        description="A stdin/stdout problem requiring JSON output.",
        difficulty="easy",
        input_output_mode="stdin_stdout",
        entry_point="main()",
        judge_config={"output_format": "json"},
        public_test_cases=[{"input": "", "expected_output": {"ok": True}}],
    )

    result = SandboxExecutor(sandbox_config).execute("print('not-json')", problem)

    assert result.all_passed is False
    assert result.test_results[0].status == "runtime_error"
    assert "valid JSON" in result.test_results[0].error_message


def test_function_judge_exact_and_nested_float_tolerance(sandbox_executor):
    """Exact comparison and recursive float tolerance are configurable."""
    exact_problem = Problem(
        problem_id="exact-float",
        title="Exact Float",
        description="A problem that requires exact output comparison.",
        difficulty="easy",
        judge_config={"comparison": "exact"},
        test_cases=[{"input": {}, "expected_output": 1.0}],
    )
    exact_result = sandbox_executor.execute(
        "def solution():\n    return 1.0000001",
        exact_problem,
    )
    assert exact_result.all_passed is False

    tolerant_problem = Problem(
        problem_id="tolerant-float",
        title="Tolerant Float",
        description="A problem that compares nested floating point values.",
        difficulty="easy",
        judge_config={"comparison": "float_tolerance", "float_tolerance": 1e-5},
        test_cases=[
            {"input": {}, "expected_output": {"values": [1.0, 2.0]}}
        ],
    )
    tolerant_result = sandbox_executor.execute(
        "def solution():\n    return {'values': [1.000001, 2.0]}",
        tolerant_problem,
    )
    assert tolerant_result.all_passed is True


def test_unordered_comparison_does_not_relax_exact_mode(sandbox_executor):
    """Only an explicit unordered judge accepts reordered list output."""
    exact_problem = Problem(
        problem_id="ordered",
        title="Ordered Output",
        description="A problem where output order is significant.",
        difficulty="easy",
        test_cases=[{"input": {}, "expected_output": [1, 2]}],
    )
    assert sandbox_executor.execute("def solution():\n    return [2, 1]", exact_problem).all_passed is False

    unordered_problem = Problem(
        problem_id="unordered",
        title="Unordered Output",
        description="A problem where output order is intentionally ignored.",
        difficulty="easy",
        judge_config={"comparison": "unordered"},
        test_cases=[{"input": {}, "expected_output": [1, 2]}],
    )
    assert sandbox_executor.execute("def solution():\n    return [2, 1]", unordered_problem).all_passed is True


def test_leetcode_method_entry_point_adapter(sandbox_executor):
    """A simple LeetCode class/method entry point is adapted safely."""
    problem = Problem(
        problem_id="leetcode-method",
        title="Two Sum Method",
        description="A method-style problem with a simple deterministic contract.",
        difficulty="easy",
        source_platform="leetcode",
        entry_point="Solution.twoSum(nums, target)",
        test_cases=[
            {"input": {"nums": [2, 7], "target": 9}, "expected_output": [0, 1]}
        ],
    )

    result = sandbox_executor.execute(
        "class Solution:\n    def twoSum(self, nums, target):\n        return [0, 1]",
        problem,
    )

    assert result.status == "success"


def test_custom_function_entry_point_adapter(sandbox_executor):
    """A non-default function entry point is invoked from test input."""
    problem = Problem(
        problem_id="custom-function",
        title="Custom Function",
        description="A function problem with an explicitly named entry point.",
        difficulty="easy",
        entry_point="solve(value)",
        test_cases=[{"input": {"value": 3}, "expected_output": 6}],
    )

    result = sandbox_executor.execute(
        "def solve(value):\n    return value * 2",
        problem,
    )

    assert result.status == "success"


def test_malformed_entry_point_is_unsupported(sandbox_executor):
    """Entry-point suffixes are rejected instead of silently truncated."""
    problem = Problem(
        problem_id="malformed-entry",
        title="Malformed Entry",
        description="A problem with an invalid entry-point declaration.",
        difficulty="easy",
        entry_point="Solution.solve(x).other()",
        test_cases=[{"input": {"x": 1}, "expected_output": 1}],
    )

    result = sandbox_executor.execute(
        "class Solution:\n    def solve(self, x):\n        return x",
        problem,
    )

    assert result.status == "unsupported"
    assert "entry point" in result.error_message


def test_unsupported_problem_type_is_structured(sandbox_executor):
    """Unsupported linked-list/tree/interactive types are not model wrong answers."""
    problem = Problem(
        problem_id="linked-list",
        title="Linked List",
        description="A linked list problem explicitly outside the supported protocol.",
        difficulty="medium",
        unsupported_reason="linked-list node serialization is not supported yet",
        test_cases=[{"input": {}, "expected_output": None}],
    )

    result = sandbox_executor.execute("def solution(): return None", problem)

    assert result.status == "unsupported"
    assert result.all_passed is False
    assert "linked-list" in result.error_message


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

    assert result.status == "timeout"
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
