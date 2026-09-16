"""
Tests for strategy implementations.
"""

import pytest
from unittest.mock import Mock

from src.llm_client import LLMClient
from src.models import (
    LLMConfig,
    LLMResponse,
    Problem,
    SandboxConfig,
    SandboxResult,
    StrategyConfig,
    TestCase,
    TestCaseResult,
    TokenUsage,
)
from src.sandbox_executor import SandboxExecutor
from src.strategies.vanilla import VanillaStrategy
from src.strategies.chain_of_thought import ChainOfThoughtStrategy
from src.strategies.multi_round_feedback import MultiRoundFeedbackStrategy


@pytest.fixture
def mock_llm_client():
    """Mock LLM client."""
    mock = Mock(spec=LLMClient)
    return mock


@pytest.fixture
def mock_sandbox():
    """Mock sandbox executor."""
    mock = Mock(spec=SandboxExecutor)
    return mock


@pytest.fixture
def sample_problem():
    """Sample problem fixture."""
    return Problem(
        problem_id="test-001",
        title="Two Sum",
        description="Find two numbers that add up to target",
        difficulty="easy",
        tags=["array"],
        test_cases=[
            TestCase(input={"nums": [2, 7, 11, 15], "target": 9}, expected_output=[0, 1]),
            TestCase(input={"nums": [3, 2, 4], "target": 6}, expected_output=[1, 2]),
        ],
    )


@pytest.fixture
def strategy_config():
    """Strategy configuration fixture."""
    return StrategyConfig(
        name="test-strategy",
        max_iterations=3,
    )


def test_vanilla_strategy_success(mock_llm_client, mock_sandbox, sample_problem, strategy_config):
    """Test vanilla strategy with successful solution."""
    # Mock LLM response with code
    llm_response = LLMResponse(
        text="""```python
def solution(nums, target):
    return [0, 1]
```""",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )
    mock_llm_client.generate.return_value = llm_response

    # Mock successful sandbox execution
    sandbox_result = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed",
            ),
            TestCaseResult(
                test_case_index=1,
                passed=True,
                actual_output=[1, 2],
                expected_output=[1, 2],
                execution_time=0.01,
                status="passed",
            ),
        ],
        execution_time=0.02,
        all_passed=True,
    )
    mock_sandbox.execute.return_value = sandbox_result

    # Execute strategy
    strategy = VanillaStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    # Verify
    assert result.success is True
    assert result.problem_id == "test-001"
    assert result.strategy == "test-strategy"
    assert len(result.iterations) == 1
    assert result.iterations[0].code_extracted is not None
    assert result.final_result.all_passed is True


def test_vanilla_strategy_no_code(mock_llm_client, mock_sandbox, sample_problem, strategy_config):
    """Test vanilla strategy when LLM returns no code."""
    # Mock LLM response without code
    llm_response = LLMResponse(
        text="I cannot solve this problem.",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=20, total_tokens=120),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )
    mock_llm_client.generate.return_value = llm_response

    # Execute strategy
    strategy = VanillaStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    # Verify
    assert result.success is False
    assert result.iterations[0].code_extracted is None
    assert result.final_result is None


def test_cot_strategy_success(mock_llm_client, mock_sandbox, sample_problem, strategy_config):
    """Test Chain of Thought strategy."""
    # Mock LLM response with reasoning and code
    llm_response = LLMResponse(
        text="""**Analysis:**
This is a classic two sum problem.

**Approach:**
Use a hash map to store seen numbers.

**Solution:**
```python
def solution(nums, target):
    seen = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return [seen[complement], i]
        seen[num] = i
```""",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=100, total_tokens=250),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )
    mock_llm_client.generate.return_value = llm_response

    # Mock successful sandbox execution
    sandbox_result = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed",
            ),
        ],
        execution_time=0.01,
        all_passed=True,
    )
    mock_sandbox.execute.return_value = sandbox_result

    # Execute strategy
    strategy = ChainOfThoughtStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    # Verify
    assert result.success is True
    assert len(result.iterations) == 1


def test_multi_round_feedback_converges(mock_llm_client, mock_sandbox, sample_problem, strategy_config):
    """Test multi-round feedback converges to solution."""
    # First attempt fails
    llm_response_1 = LLMResponse(
        text="""```python
def solution(nums, target):
    return [0, 0]  # Wrong
```""",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )

    # Second attempt succeeds
    llm_response_2 = LLMResponse(
        text="""```python
def solution(nums, target):
    return [0, 1]  # Correct
```""",
        usage=TokenUsage(prompt_tokens=150, completion_tokens=40, total_tokens=190),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )

    mock_llm_client.generate.side_effect = [llm_response_1, llm_response_2]

    # First sandbox result: failed
    sandbox_result_1 = SandboxResult(
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[0, 0],
                expected_output=[0, 1],
                error_message="Expected [0, 1], got [0, 0]",
                execution_time=0.01,
                status="wrong_answer",
            ),
        ],
        execution_time=0.01,
        all_passed=False,
    )

    # Second sandbox result: success
    sandbox_result_2 = SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=True,
                actual_output=[0, 1],
                expected_output=[0, 1],
                execution_time=0.01,
                status="passed",
            ),
        ],
        execution_time=0.01,
        all_passed=True,
    )

    mock_sandbox.execute.side_effect = [sandbox_result_1, sandbox_result_2]

    # Execute strategy
    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    # Verify
    assert result.success is True
    assert len(result.iterations) == 2
    assert result.iterations[0].sandbox_result.all_passed is False
    assert result.iterations[1].sandbox_result.all_passed is True


def test_multi_round_feedback_max_iterations(mock_llm_client, mock_sandbox, sample_problem, strategy_config):
    """Test multi-round feedback respects max iterations."""
    # All attempts fail
    llm_response = LLMResponse(
        text="""```python
def solution(nums, target):
    return []  # Wrong
```""",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=30, total_tokens=130),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )
    mock_llm_client.generate.return_value = llm_response

    sandbox_result = SandboxResult(
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[],
                expected_output=[0, 1],
                error_message="Expected [0, 1], got []",
                execution_time=0.01,
                status="wrong_answer",
            ),
        ],
        execution_time=0.01,
        all_passed=False,
    )
    mock_sandbox.execute.return_value = sandbox_result

    # Execute strategy
    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    # Verify
    assert result.success is False
    assert len(result.iterations) == 3  # max_iterations
    assert all(not it.sandbox_result.all_passed for it in result.iterations)


def test_extract_code_with_python_marker():
    """Test extracting code from response with python marker."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """Here's my solution:

```python
def solution(x):
    return x * 2
```

This should work!"""

    code = strategy.extract_code(response)
    assert code == "def solution(x):\n    return x * 2"


def test_extract_code_without_marker():
    """Test extracting code from response without language marker."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """```
def solution(x):
    return x * 2
```"""

    code = strategy.extract_code(response)
    assert code == "def solution(x):\n    return x * 2"


def test_extract_code_fallback():
    """Test fallback code extraction when no code block."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """def solution(x):
    return x * 2"""

    code = strategy.extract_code(response)
    assert "def solution(x):" in code


def test_extract_code_strips_appended_test_driver():
    """Test that appended module-level test driver code is truncated."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """```python
def solution(nums, target):
    num_dict = {}
    for i, num in enumerate(nums):
        complement = target - num
        if complement in num_dict:
            return [num_dict[complement], i]
        num_dict[num] = i
    return []

# Test Cases
test_cases = [
    {'nums': [2, 7, 11, 15], 'target': 9},
]

for test in test_cases:
    print(solution(**test))
```"""

    code = strategy.extract_code(response)
    assert "test_cases = [" not in code
    assert "for test in test_cases" not in code
    assert code.endswith("return []")


def test_extract_code_keeps_helper_definitions_after_solution():
    """Test that def/class/imports after solution are preserved."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """```python
def solution(x):
    return helper(x) * 2

def helper(x):
    return x + 1

if __name__ == "__main__":
    print(solution(3))
```"""

    code = strategy.extract_code(response)
    assert "def helper(x):" in code
    assert 'if __name__' not in code
    assert "print(" not in code


def test_extract_code_keeps_solution_only_response():
    """Test that a clean response is returned unchanged."""
    config = StrategyConfig(name="test")
    llm_client = Mock()
    sandbox = Mock()
    strategy = VanillaStrategy(config, llm_client, sandbox)

    response = """```python
import heapq

def solution(lists):
    return heapq
```"""

    code = strategy.extract_code(response)
    assert code == "import heapq\n\ndef solution(lists):\n    return heapq"
