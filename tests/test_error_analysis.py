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
