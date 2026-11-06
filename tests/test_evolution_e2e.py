"""End-to-end tests for code evolution analysis feature."""

import json
from unittest.mock import MagicMock

import pytest
from structlog.testing import capture_logs

from src.experiment_report import _analyze_quality_evolution
from src.harness import AlgorithmHarness
from src.models import (
    CodeQualityMetrics,
    HarnessConfig,
    LLMConfig,
    LLMResponse,
    SandboxResult,
    StrategyConfig,
    TokenUsage,
)

FIRST_CODE = "def solution(nums):\n    return 0"
FINAL_CODE = """def solution(nums):
    total = 0
    for i in range(len(nums)):
        for j in range(len(nums)):
            if i == j:
                total += nums[i]
    return total"""


@pytest.fixture
def run_multi_round(tmp_path, monkeypatch):
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "sum",
                    "title": "Sum",
                    "description": "Return the sum of the numbers.",
                    "difficulty": "easy",
                    "entry_point": "solution(nums)",
                    "public_test_cases": [{"input": {"nums": [1, 2, 3]}, "expected_output": 6}],
                }
            ]
        ),
        encoding="utf-8",
    )

    def run(rounds, *, quality=True, evolution=True, fail_analysis=False):
        config = HarnessConfig(
            dataset_path=str(dataset),
            llm_config=LLMConfig(provider="openai", api_key="test-key", model="test-model"),
            strategies=[StrategyConfig(name="multi_round_feedback", max_iterations=len(rounds))],
            enable_quality_analysis=quality,
            enable_evolution_analysis=evolution,
            quality_analysis_config={
                "enable_space_analysis": False,
                "enable_readability_analysis": False,
                "enable_style_analysis": False,
            },
        )
        harness = AlgorithmHarness(config)
        client = MagicMock()
        client.generate.side_effect = [
            LLMResponse(
                text=f"```python\n{code}\n```" if code else "I have no solution yet.",
                usage=TokenUsage(prompt_tokens=50, completion_tokens=50, total_tokens=100),
                model="test-model",
            )
            for code, _ in rounds
        ]
        sandbox = MagicMock()
        sandbox.health_check.return_value = (True, "OK")
        sandbox.execute.side_effect = [
            SandboxResult(status="success" if passed else "failed", all_passed=passed)
            for code, passed in rounds
            if code
        ]
        monkeypatch.setattr("src.harness.LLMClient", lambda config: client)
        monkeypatch.setattr("src.harness.SandboxExecutor", lambda config: sandbox)
        if fail_analysis:
            time_analyzer = harness.quality_analyzer.time_analyzer
            analyze = time_analyzer.analyze

            def analyze_time(code, *args):
                if code == FIRST_CODE:
                    raise ValueError("unavailable quality analysis")
                return analyze(code, *args)

            monkeypatch.setattr(time_analyzer, "analyze", analyze_time)

        with capture_logs() as logs:
            harness.run()
        result = harness.results["multi_round_feedback"][0]

        assert result.success
        assert result.generated_code == FINAL_CODE
        assert sandbox.execute.call_count == sum(bool(code) for code, _ in rounds)
        summary = _analyze_quality_evolution(
            {"combo": [json.loads(result.model_dump_json())]}, tmp_path
        )
        return result, logs, summary

    return run


@pytest.mark.parametrize("quality,evolution", [(True, True), (True, False), (False, True)])
def test_harness_produces_round_quality_and_report(run_multi_round, quality, evolution):
    result, logs, summary = run_multi_round(
        [(FIRST_CODE, False), (FINAL_CODE, True)], quality=quality, evolution=evolution
    )

    first, final = result.iterations
    assert first.sandbox_result.status == "failed"
    assert final.sandbox_result.status == "success"
    if quality:
        assert first.code_quality is not None
        assert final.code_quality is not None
        assert first.code_quality.time_complexity.static_analysis == "O(1)"
        assert final.code_quality.time_complexity.static_analysis == "O(n^2)"
        assert result.quality_metrics == final.code_quality
    else:
        assert first.code_quality is final.code_quality is result.quality_metrics is None

    should_analyze = quality and evolution
    assert any(entry["event"] == "quality_drops_detected" for entry in logs) == should_analyze
    assert summary["has_evolution_data"] is should_analyze
    assert summary["total_drops"] == (2 if should_analyze else 0)
    assert summary["charts_generated"] == (["evolution_sum.png"] if should_analyze else [])


@pytest.mark.parametrize(
    "rounds,fail_analysis",
    [
        ([(None, False), (FINAL_CODE, True)], False),
        ([(FIRST_CODE, False), (FINAL_CODE, True)], True),
        ([(FINAL_CODE, True)], False),
    ],
)
def test_harness_skips_evolution_without_comparable_rounds(run_multi_round, rounds, fail_analysis):
    result, logs, summary = run_multi_round(rounds, fail_analysis=fail_analysis)

    assert [item.code_quality is not None for item in result.iterations] == [
        *([False] * (len(rounds) - 1)),
        True,
    ]
    assert result.quality_metrics == result.iterations[-1].code_quality
    assert not any(entry["event"] == "quality_drops_detected" for entry in logs)
    assert summary["has_evolution_data"] is False


def test_evolution_chart_generation_in_reports(tmp_path):
    """Test that evolution charts are generated when included in experiment reports."""
    from src.experiment_report import _analyze_quality_evolution
    from src.models import ExecutionResult, IterationResult

    # Create mock result with quality evolution
    result = ExecutionResult(
        problem_id="chart_test",
        strategy="multi_round",
        generated_code="def solution(): pass",
        status="success",
        iterations=[
            IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=80.0)),
            IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=60.0)),
            IterationResult(iteration=3, code_quality=CodeQualityMetrics(overall_score=75.0)),
        ],
    )

    raw_results = {"combo1": [result.model_dump()]}

    # Run analysis
    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    # Verify charts were generated
    assert analysis["has_evolution_data"] is True
    assert len(analysis["charts_generated"]) > 0

    # Verify chart files exist
    for chart_name in analysis["charts_generated"]:
        chart_path = tmp_path / chart_name
        assert chart_path.exists()
        assert chart_path.stat().st_size > 0


def test_complete_workflow_with_evolution_analysis(tmp_path):
    """Test complete workflow from execution to report generation with evolution analysis."""
    from src.experiment_report import _analyze_quality_evolution
    from src.models import ExecutionResult, IterationResult

    # Simulate a complete experiment with multiple problems
    results_with_evolution = [
        ExecutionResult(
            problem_id="problem1",
            strategy="multi_round",
            generated_code="def solution(): pass",
            status="success",
            iterations=[
                IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=85.0)),
                IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=65.0)),
            ],
        ),
        ExecutionResult(
            problem_id="problem2",
            strategy="multi_round",
            generated_code="def solution(): pass",
            status="success",
            iterations=[
                IterationResult(iteration=1, code_quality=CodeQualityMetrics(overall_score=75.0)),
                IterationResult(iteration=2, code_quality=CodeQualityMetrics(overall_score=80.0)),
            ],
        ),
    ]

    raw_results = {"combo1": [r.model_dump() for r in results_with_evolution]}

    # Run evolution analysis
    analysis = _analyze_quality_evolution(raw_results, tmp_path)

    # Verify analysis results
    assert analysis["has_evolution_data"] is True
    assert analysis["problems_with_drops"] >= 1
    assert analysis["total_drops"] >= 1
    assert len(analysis["drop_reasons"]) > 0

    # Verify summary structure
    assert "has_evolution_data" in analysis
    assert "problems_with_drops" in analysis
    assert "total_drops" in analysis
    assert "drop_reasons" in analysis
    assert "charts_generated" in analysis
