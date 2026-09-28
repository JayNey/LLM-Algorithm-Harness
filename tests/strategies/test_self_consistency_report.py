"""
Test Self-Consistency strategy report generation and metadata.
"""

import pytest
from unittest.mock import MagicMock, patch

from src.strategies.self_consistency import SelfConsistencyStrategy
from src.models import (
    Problem,
    TestCase,
    StrategyConfig,
    LLMResponse,
    TokenUsage,
    SandboxResult,
    TestCaseResult,
)


@pytest.fixture
def simple_problem():
    """Create a simple test problem."""
    return Problem(
        problem_id="test_voting",
        title="Test Voting",
        description="Test voting mechanism",
        difficulty="easy",
        public_test_cases=[
            TestCase(input="2 3", expected_output="5"),
        ],
        hidden_test_cases=[],
        feedback_test_cases=[],
        entry_point="solution",
    )


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client that returns varied solutions."""
    client = MagicMock()

    # Define different candidate solutions
    solutions = [
        "def solution(a, b):\n    return a + b",  # Correct solution A (will appear 3 times)
        "def solution(a, b):\n    return a + b",  # Correct solution A
        "def solution(a, b):\n    return b + a",  # Correct solution B (semantically same, syntactically different)
        "def solution(a, b):\n    return a + b",  # Correct solution A
        "def solution(a, b):\n    return a - b",  # Wrong solution
    ]

    # Mock generate method to return different solutions
    client.generate.side_effect = [
        LLMResponse(
            text=f"```python\n{sol}\n```",
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            usage_missing=False,
            effective_params={"temperature": 0.8},
        )
        for sol in solutions
    ]

    return client


@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox that validates solutions."""
    sandbox = MagicMock()

    # Mock execute to validate based on actual code logic
    def mock_execute(problem, code, stage="public"):
        # Simple validation: correct solutions pass, wrong ones fail
        if "a + b" in code or "b + a" in code:
            return SandboxResult(
                status="success",
                all_passed=True,
                test_results=[
                    TestCaseResult(
                        test_case_index=0,
                        input="2 3",
                        expected="5",
                        actual="5",
                        passed=True,
                        status="passed",
                    )
                ],
            )
        else:
            return SandboxResult(
                status="failed",
                all_passed=False,
                test_results=[
                    TestCaseResult(
                        test_case_index=0,
                        input="2 3",
                        expected="5",
                        actual="-1",
                        passed=False,
                        status="failed",
                    )
                ],
            )

    sandbox.execute.side_effect = mock_execute
    return sandbox


def test_voting_statistics_in_result(simple_problem, mock_llm_client, mock_sandbox):
    """Test that voting statistics are included in execution result."""
    config = StrategyConfig(name="self_consistency", num_candidates=5, temperature=0.8)
    strategy = SelfConsistencyStrategy(config, mock_llm_client, mock_sandbox)

    result = strategy.execute(simple_problem)

    # Verify execution succeeded
    assert result.status == "success"

    # Verify voting statistics are in llm_traces
    voting_stats = None
    for trace in result.llm_traces:
        if "voting_statistics" in trace:
            voting_stats = trace
            break

    assert voting_stats is not None, "Voting statistics not found in llm_traces"

    # Verify voting statistics structure
    assert "voting_statistics" in voting_stats
    assert "selected_code_frequency" in voting_stats
    assert "total_candidates" in voting_stats
    assert "passing_candidates" in voting_stats

    # Verify values
    assert voting_stats["total_candidates"] == 5
    assert voting_stats["passing_candidates"] == 4  # 4 out of 5 pass tests
    assert (
        voting_stats["selected_code_frequency"] == 3
    )  # Most frequent solution appears 3 times

    # Verify voting_statistics contains vote counts per code
    assert len(voting_stats["voting_statistics"]) >= 1
    assert all(
        "code" in entry and "count" in entry
        for entry in voting_stats["voting_statistics"]
    )


def test_result_serialization(simple_problem, mock_llm_client, mock_sandbox):
    """Test that execution result with voting stats can be serialized."""
    config = StrategyConfig(name="self_consistency", num_candidates=5, temperature=0.8)
    strategy = SelfConsistencyStrategy(config, mock_llm_client, mock_sandbox)

    result = strategy.execute(simple_problem)

    # Serialize to dict (this is what gets saved to JSON)
    result_dict = result.model_dump()

    # Verify serialization succeeded
    assert isinstance(result_dict, dict)
    assert "llm_traces" in result_dict
    assert len(result_dict["llm_traces"]) > 0

    # Verify voting stats survived serialization
    voting_stats = None
    for trace in result_dict["llm_traces"]:
        if "voting_statistics" in trace:
            voting_stats = trace
            break

    assert voting_stats is not None
    assert voting_stats["total_candidates"] == 5
    assert voting_stats["passing_candidates"] == 4
