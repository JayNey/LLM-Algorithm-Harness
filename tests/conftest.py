"""
Pytest configuration and shared fixtures.
"""

import pytest
from unittest.mock import Mock

from src.models import (
    Problem,
    TestCase,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
    LLMResponse,
    TokenUsage,
    SandboxResult,
    TestCaseResult,
)


@pytest.fixture
def sample_test_case():
    """Sample test case fixture."""
    return TestCase(
        input={"nums": [2, 7, 11, 15], "target": 9},
        expected_output=[0, 1]
    )


@pytest.fixture
def sample_problem(sample_test_case):
    """Sample problem fixture."""
    return Problem(
        problem_id="test-001",
        title="Two Sum",
        description="Given an array of integers nums and an integer target, return indices of the two numbers such that they add up to target.",
        difficulty="easy",
        tags=["array", "hash-table"],
        test_cases=[sample_test_case],
        constraints="2 <= nums.length <= 10^4"
    )


@pytest.fixture
def sample_llm_config():
    """Sample LLM configuration."""
    return LLMConfig(
        provider="openai",
        api_key="test-key",
        model="gpt-3.5-turbo",
        temperature=0.7,
        max_tokens=2000,
        timeout=30
    )


@pytest.fixture
def sample_sandbox_config():
    """Sample sandbox configuration."""
    return SandboxConfig(
        timeout_seconds=5,
        memory_limit_mb=256,
        allowed_imports=["math", "itertools", "collections"]
    )


@pytest.fixture
def sample_strategy_config():
    """Sample strategy configuration."""
    return StrategyConfig(
        name="vanilla",
        max_iterations=1,
        temperature=0.7,
        max_tokens=2000
    )


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    client = Mock()
    client.generate.return_value = LLMResponse(
        text="```python\ndef solution(nums, target):\n    return [0, 1]\n```",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-3.5-turbo",
        finish_reason="stop"
    )
    return client


@pytest.fixture
def mock_sandbox_executor():
    """Mock sandbox executor."""
    sandbox = Mock()
    sandbox.execute.return_value = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed"
            )
        ],
        execution_time=0.01,
        all_passed=True
    )
    return sandbox


@pytest.fixture
def sample_llm_response():
    """Sample LLM response with code."""
    return LLMResponse(
        text="""Here is the solution:

```python
def solution(nums, target):
    hash_map = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in hash_map:
            return [hash_map[complement], i]
        hash_map[num] = i
    return []
```

This uses a hash table for O(n) time complexity.""",
        usage=TokenUsage(prompt_tokens=120, completion_tokens=230, total_tokens=350),
        model="gpt-3.5-turbo",
        finish_reason="stop"
    )


@pytest.fixture
def sample_successful_sandbox_result():
    """Sample successful sandbox execution result."""
    return SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.002,
                status="passed"
            ),
            TestCaseResult(
                test_case_index=1,
                passed=True,
                actual_output=[1, 2],
                expected_output=[1, 2],
                execution_time=0.003,
                status="passed"
            )
        ],
        execution_time=0.005,
        all_passed=True
    )


@pytest.fixture
def sample_failed_sandbox_result():
    """Sample failed sandbox execution result."""
    return SandboxResult(
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.002,
                status="passed"
            ),
            TestCaseResult(
                test_case_index=1,
                passed=False,
                actual_output=[0, 0],
                expected_output=[1, 2],
                error_message="Output mismatch",
                execution_time=0.003,
                status="wrong_answer"
            )
        ],
        execution_time=0.005,
        all_passed=False
    )
