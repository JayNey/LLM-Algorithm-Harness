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


# ============================================================================
# Result recording tests (issue #13)
# ============================================================================


def _code_response(body="def solution(nums, target):\n    return [0, 0]"):
    """LLM response fixture containing an extractable code block."""
    return LLMResponse(
        text=f"```python\n{body}\n```",
        usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )


def _failing_sandbox_result():
    """Sandbox result fixture with one wrong-answer test case."""
    return SandboxResult(
        status="failed",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=False,
                actual_output=[0, 0],
                expected_output=[0, 1],
                error_message="Output mismatch",
                execution_time=0.01,
                status="wrong_answer",
            )
        ],
        execution_time=0.01,
        all_passed=False,
    )


def test_multi_round_all_failures_preserve_final_result(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """A fully failed multi-round run still exposes the last sandbox result."""
    mock_llm_client.generate.return_value = _code_response()
    mock_sandbox.execute.return_value = _failing_sandbox_result()

    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert result.success is False
    assert len(result.iterations) == strategy_config.max_iterations
    assert result.final_result is not None
    assert result.final_result.all_passed is False
    assert result.final_result.test_results[0].passed is False
    assert result.final_result.test_results[0].actual_output == [0, 0]
    assert result.test_results
    assert result.failure_category == "wrong_answer"


def test_multi_round_model_error_keeps_completed_rounds(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """A model failure mid-run keeps earlier traces and yields a terminal record."""
    mock_llm_client.generate.side_effect = [
        _code_response(),
        RuntimeError("provider unavailable"),
    ]
    mock_sandbox.execute.return_value = _failing_sandbox_result()

    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert len(result.iterations) == 2
    assert result.iterations[0].sandbox_result is not None
    assert result.iterations[0].response_text is not None
    assert result.iterations[1].llm_error is not None
    assert result.iterations[1].sandbox_result is None
    assert result.final_result is not None
    assert result.final_result.all_passed is False
    assert result.failure_category == "model_error"
    assert result.total_tokens == 150


def test_multi_round_code_extraction_failure_category(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """Responses without code mark the run as code extraction failure."""
    mock_llm_client.generate.return_value = LLMResponse(
        text="Sorry, I cannot solve this.",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        model="gpt-3.5-turbo",
        finish_reason="stop",
    )

    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert result.success is False
    assert result.final_result is None
    assert result.failure_category == "code_extraction_failed"
    assert mock_sandbox.execute.call_count == 0
    assert len(result.iterations) == strategy_config.max_iterations


def test_multi_round_feedback_prompt_includes_problem_context(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """Feedback prompts restate the problem statement and constraints."""
    problem = sample_problem.model_copy(update={"constraints": "2 <= nums.length <= 10^4"})
    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    prompt = strategy.build_feedback_prompt(
        problem, "def solution(nums, target):\n    return [0, 0]", _failing_sandbox_result(), 1
    )

    assert problem.title in prompt
    assert problem.description in prompt
    assert problem.constraints in prompt
    assert "Output mismatch" in prompt


def test_vanilla_sandbox_exception_records_reason(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """Vanilla keeps the sandbox failure reason instead of dropping it."""
    mock_llm_client.generate.return_value = _code_response()
    mock_sandbox.execute.side_effect = Exception("sandbox boom")

    strategy = VanillaStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert result.success is False
    assert result.final_result is None
    assert result.iterations[0].sandbox_error == "sandbox boom"
    assert result.failure_category == "system_error"


def test_vanilla_model_error_returns_terminal_result(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """Vanilla turns model API errors into a recorded model_error result."""
    mock_llm_client.generate.side_effect = RuntimeError("provider unavailable")

    strategy = VanillaStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert result.success is False
    assert result.failure_category == "model_error"
    assert result.iterations[0].llm_error == "provider unavailable"
    assert result.final_result is None


def test_execution_result_llm_traces_redacted_and_timed(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """Traces carry redacted prompts/responses and measured wall-clock time."""
    mock_llm_client.generate.return_value = _code_response(
        "def solution(nums, target):\n    return [0, 0]  # Bearer sk-live-secret"
    )
    mock_sandbox.execute.return_value = _failing_sandbox_result()

    strategy = VanillaStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert result.execution_time_seconds > 0
    assert len(result.llm_traces) == 1
    trace = result.llm_traces[0]
    assert trace["iteration"] == 1
    assert trace["prompt_tokens"] == 100
    assert "[REDACTED]" in trace["response_text"]
    assert "sk-live-secret" not in str(result.llm_traces)
    assert "sk-live-secret" not in (result.iterations[0].response_text or "")
    assert result.iterations[0].elapsed_seconds >= 0


def test_multi_round_final_round_extraction_failure_category(
    mock_llm_client, mock_sandbox, sample_problem, strategy_config
):
    """A run ending on extraction failure is classified as such even when
    earlier rounds produced sandbox results."""
    responses = [
        _code_response(),
        LLMResponse(
            text="Sorry, I cannot solve this.",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="gpt-3.5-turbo",
            finish_reason="stop",
        ),
        LLMResponse(
            text="Sorry, I still cannot solve this.",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="gpt-3.5-turbo",
            finish_reason="stop",
        ),
    ]
    mock_llm_client.generate.side_effect = responses
    mock_sandbox.execute.return_value = _failing_sandbox_result()

    strategy = MultiRoundFeedbackStrategy(strategy_config, mock_llm_client, mock_sandbox)
    result = strategy.execute(sample_problem)

    assert len(result.iterations) == 3
    assert result.final_result is not None
    assert result.final_result.all_passed is False
    assert result.failure_category == "code_extraction_failed"
