"""Focused checks and a hand-labeled offline gold set for issue #89."""

import json
from collections import Counter
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.failure_classifier import MODES, FailureClassification, classify_failure_mode

GOLD_PATH = Path(__file__).parent / "fixtures" / "failure_modes_gold.json"


def test_hand_labeled_gold_accuracy_and_mode_coverage():
    rows = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    expected_counts = Counter(row["expected_mode"] for row in rows)
    assert set(MODES).issubset(expected_counts)
    assert all(expected_counts[mode] >= 3 for mode in MODES)
    assert expected_counts[None] >= 4

    eligible = [row for row in rows if row["expected_mode"] is not None]
    assert len(eligible) >= 25
    predictions = [classify_failure_mode(row["result"], row.get("problem")) for row in rows]
    correct = sum(
        prediction is not None and prediction.mode == row["expected_mode"]
        for row, prediction in zip(rows, predictions, strict=True)
        if row["expected_mode"] is not None
    )
    assert correct / len(eligible) > 0.85, [
        (row["id"], row["expected_mode"], prediction.mode if prediction else None)
        for row, prediction in zip(rows, predictions, strict=True)
        if row["expected_mode"] is not None
        and (prediction is None or prediction.mode != row["expected_mode"])
    ]
    assert all(
        prediction is None
        for row, prediction in zip(rows, predictions, strict=True)
        if row["expected_mode"] is None
    )


def test_decisions_are_immutable_bounded_and_reason_codes_only():
    rows = json.loads(GOLD_PATH.read_text(encoding="utf-8"))
    for row in rows:
        prediction = classify_failure_mode(row["result"], row.get("problem"))
        if prediction is None:
            continue
        assert 0 <= prediction.confidence <= 1
        assert prediction.mode in MODES
        assert prediction.evidence
        assert all(
            ":" in reason and reason.replace(":", "").replace("_", "").isalnum()
            for reason in prediction.evidence
        )
        assert "SECRET_HIDDEN_VALUE" not in repr(prediction)

    immutable = FailureClassification("logic_error", 0.8, ("sandbox:wrong_answer",))
    with pytest.raises(FrozenInstanceError):
        immutable.mode = "unknown"


def test_hidden_empty_input_alone_does_not_imply_boundary_failure():
    result = {
        "status": "failed",
        "failure_category": "wrong_answer",
        "final_result": {"status": "success", "all_passed": True},
        "hidden_result": {
            "status": "failed",
            "all_passed": False,
            "test_results": [{"passed": False, "status": "wrong_answer"}],
        },
    }
    problem = {"hidden_test_cases": [{"input": {"items": []}, "expected_output": "SECRET"}]}
    prediction = classify_failure_mode(result, problem)
    assert prediction is not None and prediction.mode == "logic_error"
    assert "SECRET" not in repr(prediction)


def test_public_empty_failure_needs_ordinary_pass_in_same_stage():
    result = {
        "status": "failed",
        "failure_category": "wrong_answer",
        "final_result": {
            "status": "failed",
            "test_results": [
                {"passed": False, "status": "wrong_answer"},
                {"passed": True, "status": "passed"},
            ],
        },
    }
    problem = {
        "public_test_cases": [{"input": {"items": []}}],
        "feedback_test_cases": [{"input": {"items": [1, 2]}}],
    }
    prediction = classify_failure_mode(result, problem)
    assert prediction is not None and prediction.mode == "logic_error"


def test_runtime_exception_on_empty_input_with_normal_pass_is_boundary():
    result = {
        "status": "failed",
        "failure_category": "system_error",
        "final_result": {
            "status": "failed",
            "test_results": [
                {"passed": False, "status": "runtime_error", "error_message": "IndexError"},
                {"passed": True, "status": "passed"},
            ],
        },
    }
    problem = {
        "public_test_cases": [
            {"input": {"items": []}},
            {"input": {"items": [1, 2]}},
        ]
    }
    prediction = classify_failure_mode(result, problem)
    assert prediction is not None and prediction.mode == "boundary_condition"
    assert "visible_case:empty_or_singleton_failed" in prediction.evidence


def test_explicit_signature_mismatch_is_understanding_not_generic_runtime():
    result = {
        "status": "error",
        "failure_category": "system_error",
        "final_result": {
            "status": "failed",
            "test_results": [
                {
                    "passed": False,
                    "status": "runtime_error",
                    "error_message": (
                        "TypeError: solution() got an unexpected keyword argument 'nums'"
                    ),
                }
            ],
        },
    }
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "understanding_error"


def test_generic_exception_and_single_type_mismatch_do_not_imply_understanding():
    result = {
        "status": "failed",
        "failure_category": "wrong_answer",
        "final_result": {
            "status": "failed",
            "test_results": [
                {
                    "passed": False,
                    "status": "wrong_answer",
                    "expected_output": [1],
                    "actual_output": "1",
                }
            ],
        },
    }
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "logic_error"


@pytest.mark.parametrize("provider_message", ["Request timed out", "SyntaxError in API response"])
def test_model_error_message_does_not_become_algorithm_timeout_or_syntax(provider_message):
    result = {
        "status": "error",
        "failure_category": "model_error",
        "iterations": [{"llm_error": provider_message}],
        "error_message": provider_message,
    }
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "infrastructure_error"


def test_terminal_llm_error_beats_generic_timeout_message():
    result = {"status": "error", "iterations": [{"llm_error": "Request timed out"}]}
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "infrastructure_error"


def test_stale_sandbox_timeout_does_not_override_terminal_model_error():
    result = {
        "status": "failed",
        "failure_category": "model_error",
        "final_result": {"status": "timeout"},
        "iterations": [{"llm_error": "Request timed out"}],
    }
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "infrastructure_error"


def test_wrong_answer_output_text_is_not_exception_or_boundary_evidence():
    result = {
        "status": "failed",
        "failure_category": "wrong_answer",
        "final_result": {
            "status": "failed",
            "test_results": [{
                "passed": False,
                "status": "wrong_answer",
                "expected_output": "SyntaxError",
                "actual_output": "timeout edge case",
                "error_message": "Expected SyntaxError, got timeout edge case",
            }],
        },
    }
    prediction = classify_failure_mode(result)
    assert prediction is not None and prediction.mode == "logic_error"


def test_unrecorded_execution_placeholder_is_not_a_failure():
    result = {"status": "error", "evaluation_completed": False,
              "error_message": "Task unit did not produce a result"}
    assert classify_failure_mode(result) is None


def test_boundary_contrast_can_explain_runtime_exception_on_empty_case():
    result = {
        "status": "failed",
        "failure_category": "system_error",
        "final_result": {
            "status": "failed",
            "test_results": [
                {"passed": True, "status": "passed"},
                {
                    "passed": False,
                    "status": "runtime_error",
                    "error_message": "IndexError: list index out of range",
                },
            ],
        },
    }
    problem = {
        "public_test_cases": [{"input": {"nums": [1, 2]}}, {"input": {"nums": []}}]
    }
    prediction = classify_failure_mode(result, problem)
    assert prediction is not None and prediction.mode == "boundary_condition"


def test_ambiguous_test_stage_does_not_use_problem_input_for_boundary():
    result = {
        "status": "failed",
        "failure_category": "wrong_answer",
        "final_result": {
            "status": "failed",
            "test_results": [{"passed": False, "status": "wrong_answer"}],
        },
    }
    problem = {
        "public_test_cases": [{"input": {"items": []}}],
        "feedback_test_cases": [{"input": {"items": [1, 2]}}],
    }
    prediction = classify_failure_mode(result, problem)
    assert prediction is not None and prediction.mode == "logic_error"
