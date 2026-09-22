"""
End-to-end test for Self-Consistency strategy report generation.

Verifies that the execution result contains all candidates and voting statistics
that can be used for report generation.
"""

import json
from unittest.mock import MagicMock

import pytest

from src.models import (
    Problem,
    SandboxResult,
    StrategyConfig,
    TestCase,
    TestCaseResult,
    LLMResponse,
    TokenUsage,
)
from src.strategies.self_consistency import SelfConsistencyStrategy


@pytest.fixture
def simple_problem():
    """Create a simple two-sum problem for testing."""
    return Problem(
        problem_id="two_sum_test",
        title="Two Sum",
        description="Given two numbers, return their sum.",
        difficulty="easy",
        test_cases=[
            TestCase(
                test_case_index=0,
                input="2 3",
                expected_output="5",
                visibility="public",
            )
        ],
    )


@pytest.fixture
def mock_llm_client():
    """Create a mock LLM client that generates diverse solutions."""
    client = MagicMock()

    # Generate 5 different responses with some duplicates
    solutions = [
        "```python\ndef solve():\n    a, b = map(int, input().split())\n    return a + b\n```",
        "```python\ndef solve():\n    a, b = map(int, input().split())\n    return a + b\n```",  # Duplicate
        "```python\ndef solve():\n    a, b = map(int, input().split())\n    return a + b\n```",  # Duplicate
        "```python\ndef solve():\n    nums = list(map(int, input().split()))\n    return nums[0] + nums[1]\n```",  # Different approach
        "```python\ndef solve():\n    return sum(map(int, input().split()))\n```",  # Another approach
    ]

    # Create proper LLMResponse objects
    mock_responses = [
        LLMResponse(
            text=sol,
            usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            model="gpt-4",
            finish_reason="stop",
            reasoning_text="",  # Empty reasoning text
        )
        for sol in solutions
    ]

    client.generate.side_effect = mock_responses

    return client


@pytest.fixture
def mock_sandbox():
    """Create a mock sandbox that validates all solutions."""
    sandbox = MagicMock()

    def mock_execute(problem, code, stage="public"):
        # All valid solutions pass
        return SandboxResult(
            status="success",
            all_passed=True,
            test_results=[
                TestCaseResult(
                    test_case_index=0,
                    input="2 3",
                    expected_output="5",
                    actual_output="5",
                    passed=True,
                    status="passed",
                )
            ],
        )

    sandbox.execute.side_effect = mock_execute
    return sandbox


def test_e2e_execution_result_contains_all_candidates_and_voting_stats(
    simple_problem, mock_llm_client, mock_sandbox
):
    """
    End-to-end test: verify execution result contains all candidates and voting statistics.

    This verifies that the ExecutionResult has all necessary information for report generation.
    """
    # Setup strategy
    config = StrategyConfig(
        name="self_consistency",
        num_candidates=5,
        temperature=0.8,
    )
    strategy = SelfConsistencyStrategy(config, mock_llm_client, mock_sandbox)

    # Execute strategy
    execution_result = strategy.execute(simple_problem)

    # Verify execution succeeded
    assert execution_result.status == "success"

    # Verify all 5 candidates are recorded in iterations
    assert len(execution_result.iterations) == 5
    print(f"\n✓ All 5 candidates recorded in iterations")

    # Verify each iteration has necessary fields
    for i, iteration in enumerate(execution_result.iterations, 1):
        assert iteration.iteration == i
        assert iteration.code_extracted is not None
        assert iteration.sandbox_result is not None
        print(f"✓ Iteration {i} has complete data")

    # Verify voting statistics in llm_traces
    voting_stats_found = False
    for trace in execution_result.llm_traces:
        if "voting_statistics" in trace:
            voting_stats_found = True

            # Verify required fields
            assert "selected_code_frequency" in trace
            assert "total_candidates" in trace
            assert "passing_candidates" in trace
            assert "voting_statistics" in trace

            # Verify values
            assert trace["total_candidates"] == 5
            assert trace["passing_candidates"] == 5
            assert trace["selected_code_frequency"] == 3  # Most common appears 3 times

            # Verify voting_statistics is a list of dicts
            voting_stats = trace["voting_statistics"]
            assert isinstance(voting_stats, list)
            assert len(voting_stats) >= 1

            # Verify each entry has code and count
            for entry in voting_stats:
                assert "code" in entry
                assert "count" in entry
                assert isinstance(entry["count"], int)
                assert entry["count"] > 0

            print(
                f"✓ Voting statistics present with {len(voting_stats)} unique solutions"
            )
            print(
                f"✓ Selected solution appears {trace['selected_code_frequency']} times"
            )
            break

    assert voting_stats_found, "Voting statistics not found in llm_traces"

    # Verify final code is selected
    assert execution_result.generated_code is not None
    assert len(execution_result.generated_code) > 0
    print(f"✓ Final code selected from voting")

    print("\n✓ ExecutionResult contains complete information for report generation")


def test_execution_result_serialization_with_voting_stats(
    simple_problem, mock_llm_client, mock_sandbox
):
    """
    Verify that execution result with voting stats can be serialized to JSON.

    This ensures the data can be persisted and used for report generation later.
    """
    config = StrategyConfig(name="self_consistency", num_candidates=5, temperature=0.8)
    strategy = SelfConsistencyStrategy(config, mock_llm_client, mock_sandbox)

    result = strategy.execute(simple_problem)

    # Serialize to JSON
    result_dict = result.model_dump()
    result_json = json.dumps(result_dict, indent=2)

    # Deserialize back
    parsed = json.loads(result_json)

    # Verify structure is preserved
    assert "iterations" in parsed
    assert len(parsed["iterations"]) == 5
    assert "llm_traces" in parsed

    # Verify voting statistics survived serialization
    voting_stats_found = False
    for trace in parsed["llm_traces"]:
        if "voting_statistics" in trace:
            voting_stats_found = True
            assert "selected_code_frequency" in trace
            assert "total_candidates" in trace
            assert "passing_candidates" in trace

            # Verify voting_statistics structure
            voting_stats = trace["voting_statistics"]
            assert isinstance(voting_stats, list)
            for entry in voting_stats:
                assert "code" in entry
                assert "count" in entry
            break

    assert voting_stats_found, "Voting statistics lost during serialization"
    print(
        "\n✓ ExecutionResult with voting stats successfully serialized and deserialized"
    )
