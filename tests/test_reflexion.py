"""Tests for the Reflexion strategy."""

from unittest.mock import Mock

from src.budget import BudgetExhausted
from src.code_quality.models import CodeQualityMetrics  # noqa: F401 - resolve model forward ref
from src.llm_client import LLMClient
from src.models import (
    ExecutionResult,
    LLMResponse,
    Problem,
    SandboxResult,
    StrategyConfig,
    TestCase,
    TestCaseResult,
    TokenUsage,
)
from src.sandbox_executor import SandboxExecutor
from src.strategies.reflexion import ReflexionStrategy

ExecutionResult.model_rebuild()


def _response(text: str, prompt: int = 10, completion: int = 5, cost: float | None = None):
    pricing = {"total_cost": cost, "model": "test-model"} if cost is not None else None
    return LLMResponse(
        text=text,
        usage=TokenUsage(
            prompt_tokens=prompt,
            completion_tokens=completion,
            total_tokens=prompt + completion,
        ),
        model="test-model",
        pricing_metadata=pricing,
    )


def _result(passed: bool) -> SandboxResult:
    return SandboxResult(
        status="success",
        test_results=[
            TestCaseResult(
                test_case_index=0,
                passed=passed,
                actual_output=[0, 1] if passed else [0, 0],
                expected_output=[0, 1],
                status="passed" if passed else "wrong_answer",
            )
        ],
        all_passed=passed,
    )


def _problem(include_feedback: bool = False) -> Problem:
    return Problem(
        problem_id="reflexion-001",
        title="Two Sum",
        description="Return the indices of two values whose sum equals target.",
        difficulty="easy",
        public_test_cases=[
            TestCase(input={"nums": [2, 7], "target": 9}, expected_output=[0, 1])
        ],
        feedback_test_cases=(
            [TestCase(input={"nums": [1, 8], "target": 9}, expected_output=[0, 1])]
            if include_feedback
            else []
        ),
        hidden_test_cases=[
            TestCase(
                input={"nums": ["SECRET"], "target": 6},
                expected_output="SECRET",
            )
        ],
    )


def test_reflexion_reflects_before_retry_and_records_costs():
    llm = Mock(spec=LLMClient)
    sandbox = Mock(spec=SandboxExecutor)
    llm.generate.side_effect = [
        _response("```python\ndef solution(nums, target):\n    return [0, 0]\n```", cost=0.2),
        _response("The duplicate-value case needs a hash map and a later complement lookup.", cost=0.3),
        _response("```python\ndef solution(nums, target):\n    return [0, 1]\n```", cost=0.4),
    ]
    sandbox.execute.side_effect = [_result(False), _result(True)]

    strategy = ReflexionStrategy(
        StrategyConfig(name="reflexion", max_iterations=2), llm, sandbox
    )
    result = strategy.execute(_problem())

    assert result.success
    assert len(result.iterations) == 2
    assert result.iterations[0].reflection_text.startswith("The duplicate-value")
    assert result.iterations[0].reflection_prompt_tokens == 10
    assert result.total_tokens == (10 + 5) + (10 + 5) + (10 + 5)
    assert result.llm_traces[0]["total_tokens"] == 30
    assert result.llm_traces[0]["pricing_metadata"]["total_cost"] == 0.5
    assert "SECRET" not in "\n".join(call.args[0] for call in llm.generate.call_args_list)
    assert "duplicate-value" in llm.generate.call_args_list[2].args[0]


def test_reflexion_bounds_reflection_context():
    llm = Mock(spec=LLMClient)
    sandbox = Mock(spec=SandboxExecutor)
    llm.generate.side_effect = [
        _response("```python\ndef solution(nums, target):\n    return [0, 0]\n```"),
        _response("R" * 100),
        _response("```python\ndef solution(nums, target):\n    return [0, 1]\n```"),
    ]
    sandbox.execute.side_effect = [_result(False), _result(True)]

    strategy = ReflexionStrategy(
        StrategyConfig(
            name="reflexion",
            max_iterations=2,
            custom_params={"reflection_context_chars": 12},
        ),
        llm,
        sandbox,
    )
    result = strategy.execute(_problem())

    assert result.success
    retry_prompt = llm.generate.call_args_list[2].args[0]
    reflection_log = retry_prompt.split("Reflection log:\n", 1)[1].split(
        "\n\nUse the reflection", 1
    )[0]
    assert len(reflection_log) == 12
    assert reflection_log == "R" * 12


def test_reflexion_marks_budget_stop_during_reflection():
    llm = Mock(spec=LLMClient)
    sandbox = Mock(spec=SandboxExecutor)
    llm.generate.side_effect = [
        _response("```python\ndef solution(nums, target):\n    return [0, 0]\n```"),
        BudgetExhausted("budget_exhausted: max_calls"),
    ]
    sandbox.execute.return_value = _result(False)

    result = ReflexionStrategy(
        StrategyConfig(name="reflexion", max_iterations=3), llm, sandbox
    ).execute(_problem())

    assert result.status == "budget_exhausted"
    assert result.error_message == "budget_exhausted: max_calls"
    assert len(result.iterations) == 1


def test_reflexion_runs_public_and_feedback_stages():
    llm = Mock(spec=LLMClient)
    sandbox = Mock(spec=SandboxExecutor)
    llm.generate.return_value = _response(
        "```python\ndef solution(nums, target):\n    return [0, 1]\n```"
    )
    sandbox.execute.side_effect = [_result(True), _result(True)]

    result = ReflexionStrategy(
        StrategyConfig(name="reflexion", max_iterations=1), llm, sandbox
    ).execute(_problem(include_feedback=True))

    assert result.success
    assert [call.kwargs["stage"] for call in sandbox.execute.call_args_list] == [
        "public",
        "feedback",
    ]
    assert len(result.final_result.test_results) == 2


def test_reflexion_error_is_recorded_and_does_not_hide_retry():
    llm = Mock(spec=LLMClient)
    sandbox = Mock(spec=SandboxExecutor)
    llm.generate.side_effect = [
        _response("```python\ndef solution(nums, target):\n    return [0, 0]\n```"),
        RuntimeError("reflection provider unavailable"),
        _response("```python\ndef solution(nums, target):\n    return [0, 1]\n```"),
    ]
    sandbox.execute.side_effect = [_result(False), _result(True)]

    result = ReflexionStrategy(
        StrategyConfig(name="reflexion", max_iterations=2), llm, sandbox
    ).execute(_problem())

    assert result.success
    assert result.iterations[0].reflection_error == "reflection provider unavailable"
    assert result.iterations[0].reflection_text is None
