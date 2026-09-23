"""
Enhanced error analysis tests (issue #52).

Hand-computed fixtures cover all seven categories, pattern aggregation,
distributions and rule-based suggestions.
"""

from src.error_analysis import (
    analyze_results,
    classify_failure,
    classify_message,
    normalize_message,
    suggestions_for,
)

# ============================================================================
# Classifier (task 1)
# ============================================================================


class TestClassifyFailure:
    def test_sandbox_terminal_statuses_map_directly(self):
        assert (
            classify_failure({"status": "failed", "final_result": {"status": "timeout"}})
            == "timeout_error"
        )
        assert (
            classify_failure({"status": "failed", "final_result": {"status": "memory_error"}})
            == "memory_error"
        )
        assert (
            classify_failure({"status": "failed", "final_result": {"status": "syntax_error"}})
            == "syntax_error"
        )
        assert (
            classify_failure({"status": "failed", "final_result": {"status": "runtime_error"}})
            == "runtime_error"
        )

    def test_test_level_status_beats_missing_final(self):
        result = {
            "status": "failed",
            "final_result": {
                "status": "failed",
                "test_results": [{"passed": False, "status": "timeout", "error_message": None}],
            },
        }
        assert classify_failure(result) == "timeout_error"

    def test_api_error_from_category_and_llm_error(self):
        assert (
            classify_failure({"status": "error", "failure_category": "model_error"}) == "api_error"
        )
        result = {
            "status": "failed",
            "iterations": [{"llm_error": "Connection reset by peer"}],
        }
        assert classify_failure(result) == "api_error"

    def test_wrong_answer_is_logic_error(self):
        result = {
            "status": "failed",
            "failure_category": "wrong_answer",
            "final_result": {
                "status": "failed",
                "test_results": [{"passed": False, "status": "wrong_answer"}],
            },
        }
        assert classify_failure(result) == "logic_error"

    def test_message_regex_fallback(self):
        assert classify_message("IndexError: list index out of range") == "runtime_error"
        assert classify_message("KeyError: 'nums'") == "runtime_error"
        assert classify_message('  File "sol.py", line 3\n    def (\nSyntaxError') == "syntax_error"
        assert classify_message("Execution timed out after 5 seconds") == "timeout_error"
        assert classify_message("AssertionError: expected 2 got 3") == "logic_error"
        assert classify_message("Something utterly unclassifiable") == "unknown"

    def test_non_failure_statuses_are_not_classified(self):
        for status in ("success", "budget_exhausted", "unsupported"):
            assert classify_failure({"status": status}) == "unknown"

    def test_unknown_failure_lands_in_unknown(self):
        result = {"status": "error", "failure_category": "system_error", "error_message": "weird"}
        assert classify_failure(result) == "unknown"


# ============================================================================
# Pattern aggregation and distributions (task 2)
# ============================================================================


def test_normalize_message_aggregates_digit_variants():
    assert normalize_message("list index out of range: 3") == normalize_message(
        "list index out of range: 7"
    )
    assert "sol.py" not in normalize_message('File "/tmp/sol.py", line 2\nboom')
    assert normalize_message("") == ""


def test_analyze_results_hand_computed(tmp_path):
    problem_info = {
        "p-1": {"difficulty": "easy", "tags": ["math"]},
        "p-2": {"difficulty": "hard", "tags": ["dp"]},
        "p-3": {"difficulty": "easy", "tags": ["math", "dp"]},
    }
    results = [
        {
            "problem_id": "p-1",
            "status": "success",
        },
        {
            "problem_id": "p-2",
            "status": "failed",
            "failure_category": "wrong_answer",
            "final_result": {
                "status": "failed",
                "test_results": [
                    {"passed": False, "status": "wrong_answer", "error_message": None}
                ],
            },
        },
        {
            "problem_id": "p-3",
            "status": "failed",
            "failure_category": "wrong_answer",
            "final_result": {
                "status": "failed",
                "test_results": [
                    {
                        "passed": False,
                        "status": "runtime_error",
                        "error_message": "IndexError: list index out of range: 3",
                    }
                ],
            },
        },
        {"problem_id": "p-4", "status": "budget_exhausted"},
    ]

    analysis = analyze_results(results, problem_info)

    # p-4 is budget-exhausted: not a failure, not classified
    assert analysis["total_failures"] == 2
    assert sum(analysis["categories"].values()) == 2
    assert analysis["categories"]["logic_error"] == 1
    assert analysis["categories"]["runtime_error"] == 1

    # Digit-normalized pattern counted once
    assert analysis["top_patterns"][0]["pattern"] == "IndexError: list index out of range: N"
    assert analysis["top_patterns"][0]["count"] == 1

    # Distributions carry counts and shares
    easy = analysis["by_difficulty"]["easy"]
    assert easy["total"] == 1 and easy["categories"]["runtime_error"]["count"] == 1
    assert easy["categories"]["runtime_error"]["share"] == 1.0
    assert analysis["by_tags"]["dp"]["total"] == 2

    # IndexError refines the runtime_error suggestion
    runtime_suggestions = analysis["suggestions"]["runtime_error"]
    assert any("len()" in hint for hint in runtime_suggestions)


def test_unknown_category_gets_generic_suggestion_only():
    suggestions = suggestions_for("unknown", ["weird failure"])
    assert suggestions == ["查看完整轨迹与失败输入，先确认失败发生在哪个环节"]


# ============================================================================
# Experiment report and panel integration (task 3)
# ============================================================================


import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.experiment import ExperimentRunner
from src.models import (
    ExperimentConfig,
    LLMConfig,
    SandboxConfig,
    StrategyConfig,
    LLMResponse,
    TokenUsage,
)


def _wrong_experiment(tmp_path):
    dataset = tmp_path / "problems.json"
    dataset.write_text(
        json.dumps(
            [
                {
                    "problem_id": "ea-1",
                    "title": "Problem 1",
                    "description": "Return x plus one for the error analysis run.",
                    "difficulty": "easy",
                    "tags": ["math"],
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                },
                {
                    "problem_id": "ea-2",
                    "title": "Problem 2",
                    "description": "Return x plus one for the error analysis run.",
                    "difficulty": "medium",
                    "tags": ["dp"],
                    "test_cases": [{"input": {"x": 5}, "expected_output": 6}],
                },
            ]
        ),
        encoding="utf-8",
    )
    config = ExperimentConfig(
        name="error-analysis-e2e",
        dataset_path=str(dataset),
        output_dir=str(tmp_path / "experiments"),
        models=[LLMConfig(provider="openai", api_key="k", model="fixed-double")],
        strategies=[StrategyConfig(name="vanilla", max_iterations=1)],
        repeats=1,
        sandbox_config=SandboxConfig(backend="host"),
    )

    def factory(config):
        double = MagicMock()
        double.generate.return_value = LLMResponse(
            text="```python\ndef solution(x):\n    return x + 100\n```",
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="fixed-double",
            finish_reason="stop",
        )
        return double

    return config, factory


def test_experiment_report_and_panel_include_error_analysis(tmp_path):
    config, factory = _wrong_experiment(tmp_path)
    with patch("src.harness.LLMClient", side_effect=factory):
        exp_dir = ExperimentRunner(config, pricing_file="nonexistent.json").run()

    comparison = json.loads((exp_dir / "comparison.json").read_text(encoding="utf-8"))

    # Both problems fail with wrong answers: logic_error, denominators reconcile
    overall = comparison["error_analysis"]
    assert overall["total_failures"] == 2
    assert overall["categories"]["logic_error"] == 2
    assert sum(overall["categories"].values()) == overall["total_failures"]
    combo_analysis = comparison["combinations"][0]["error_analysis"]
    assert combo_analysis["categories"]["logic_error"] == 2

    # Distribution by difficulty covers both problems
    assert overall["by_difficulty"]["easy"]["total"] == 1
    assert overall["by_tags"]["dp"]["total"] == 1

    report_md = (exp_dir / "REPORT.md").read_text(encoding="utf-8")
    assert "## 错误分析" in report_md
    assert "logic_error 修复建议" in report_md

    panel = (exp_dir / "panel.html").read_text(encoding="utf-8")
    assert 'id="error-pie"' in panel
    assert '"error_categories"' in panel
    assert "doughnut" in panel
