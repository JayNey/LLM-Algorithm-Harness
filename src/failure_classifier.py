"""Conservative failure-mode classification for recorded execution results.

The classifier reads persisted result dictionaries and optional problem data.
Its evidence contains fixed reason codes only: neither test inputs nor model
responses are copied into a classification. In particular, a hidden failure
alone is not evidence that the model missed a boundary condition.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MODES = (
    "syntax_error",
    "logic_error",
    "timeout",
    "boundary_condition",
    "understanding_error",
    "runtime_error",
    "infrastructure_error",
    "unknown",
)

_NON_FAILURE_STATUSES = frozenset(
    {"success", "unsupported", "budget_exhausted", "cancelled", "canceled"}
)
_RUNTIME_EXCEPTIONS = re.compile(
    r"\b(?:IndexError|KeyError|TypeError|AttributeError|ValueError|NameError|"
    r"ZeroDivisionError|RuntimeError|RecursionError|OverflowError|ImportError|"
    r"ModuleNotFoundError|MemoryError)\b",
    re.IGNORECASE,
)
_SYNTAX_EXCEPTIONS = re.compile(r"\b(?:SyntaxError|IndentationError|TabError)\b", re.I)
_TIMEOUT_MESSAGE = re.compile(r"\b(?:timed? out|timeout|time limit exceeded)\b", re.I)
_INFRA_MESSAGE = re.compile(
    r"\b(?:sandbox preflight failed|sandbox backend unavailable|"
    r"docker daemon unavailable|model api unavailable)\b",
    re.I,
)
_CONTRACT_MESSAGE = re.compile(
    r"\b(?:output[- ]format (?:mismatch|error|violation)|"
    r"(?:wrong|invalid|unexpected) output format|"
    r"(?:function |entry[- ]point )?signature mismatch|"
    r"(?:input|output|return value) contract (?:mismatch|violation)|"
    r"code must (?:define|contain) (?:the configured entry point|"
    r"a ['\"]?solution['\"]? function|a stdin/stdout program)|"
    r"missing (?:\d+ )?required positional argument|"
    r"got an unexpected keyword argument|"
    r"takes \d+ positional arguments? but \d+ were given)\b",
    re.I,
)
_BOUNDARY_MARKER = re.compile(
    r"(?<![a-z0-9])(?:boundary|edge(?:[-_ ]?case)?|off[-_ ]?by[-_ ]?one)" r"(?![a-z0-9])",
    re.I,
)


@dataclass(frozen=True, slots=True)
class FailureClassification:
    """One terminal mode and safe, machine-readable reasons for the decision."""

    mode: str
    confidence: float
    evidence: tuple[str, ...]


def _as_mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _as_tests(sandbox: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    tests = sandbox.get("test_results")
    return [test for test in tests if isinstance(test, Mapping)] if isinstance(tests, list) else []


def _active_sandbox(result: Mapping[str, Any]) -> tuple[Mapping[str, Any], str]:
    hidden = _as_mapping(result.get("hidden_result"))
    if hidden and (
        hidden.get("all_passed") is False or hidden.get("status") not in (None, "success")
    ):
        return hidden, "hidden"
    return _as_mapping(result.get("final_result")), "visible"


def _messages(
    result: Mapping[str, Any], sandbox: Mapping[str, Any], tests: list[Mapping[str, Any]]
) -> list[str]:
    values = [result.get("error_message"), sandbox.get("error_message")]
    values.extend(test.get("error_message") for test in tests if not test.get("passed"))
    iterations = result.get("iterations")
    if isinstance(iterations, list) and iterations:
        last = _as_mapping(iterations[-1])
        values.extend((last.get("llm_error"), last.get("sandbox_error")))
    # The sandbox formats wrong answers as "Expected <value>, got <value>".
    # Those values are outputs, not exception diagnostics or causal evidence.
    return [
        value
        for value in values
        if isinstance(value, str)
        and value
        and not (value.lstrip().startswith("Expected ") and ", got " in value)
    ]


def _has_status(sandbox: Mapping[str, Any], tests: list[Mapping[str, Any]], status: str) -> bool:
    return sandbox.get("status") == status or any(
        test.get("status") == status for test in tests if not test.get("passed")
    )


def _case_mapping(
    problem: Mapping[str, Any] | None, stage: str, count: int
) -> list[tuple[Mapping[str, Any], str]]:
    """Map ordered result rows to cases only when their stage is unambiguous."""
    if problem is None:
        return []

    def cases(key: str) -> list[Mapping[str, Any]]:
        raw = problem.get(key)
        if not isinstance(raw, list):
            return []
        return [entry for entry in raw if isinstance(entry, Mapping)]

    if stage == "hidden":
        hidden = cases("hidden_test_cases")
        return [(case, "hidden") for case in hidden] if len(hidden) == count else []

    public = cases("public_test_cases") or cases("test_cases")
    feedback = cases("feedback_test_cases")
    if public and feedback and len(public) + len(feedback) == count:
        return [(case, "public") for case in public] + [(case, "feedback") for case in feedback]
    if len(public) == count and len(feedback) != count:
        return [(case, "public") for case in public]
    if len(feedback) == count and len(public) != count:
        return [(case, "feedback") for case in feedback]
    return []


def _is_boundary_input(value: Any) -> bool:
    if isinstance(value, (list, tuple, str)):
        return len(value) <= 1
    if isinstance(value, Mapping):
        return any(
            isinstance(part, (list, tuple, str, Mapping)) and len(part) <= 1
            for part in value.values()
        )
    return False


def _boundary_evidence(
    tests: list[Mapping[str, Any]],
    messages: list[str],
    problem: Mapping[str, Any] | None,
    stage: str,
) -> FailureClassification | None:
    failing = [test for test in tests if not test.get("passed")]
    if not failing or not all(
        test.get("status") in (None, "wrong_answer", "failed", "runtime_error") for test in failing
    ):
        return None

    mapped = _case_mapping(problem, stage, len(tests))
    for position, test in enumerate(tests):
        if test.get("passed"):
            continue
        case = mapped[position][0] if mapped else {}
        test_id = test.get("test_case_id") or case.get("test_case_id")
        if isinstance(test_id, str) and _BOUNDARY_MARKER.search(test_id):
            return FailureClassification("boundary_condition", 0.96, ("failed_case:boundary_id",))

    if any(_BOUNDARY_MARKER.search(message) for message in messages):
        return FailureClassification("boundary_condition", 0.91, ("message:boundary_marker",))

    if not mapped or stage == "hidden":
        return None
    for position, (case, source) in enumerate(mapped):
        if tests[position].get("passed") or not _is_boundary_input(case.get("input")):
            continue
        if any(
            tests[other].get("passed")
            and other_source == source
            and not _is_boundary_input(other_case.get("input"))
            for other, (other_case, other_source) in enumerate(mapped)
        ):
            return FailureClassification(
                "boundary_condition",
                0.82,
                ("visible_case:empty_or_singleton_failed", "same_stage:ordinary_case_passed"),
            )
    return None


def _type_family(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (list, tuple)):
        return "sequence"
    if isinstance(value, Mapping):
        return "mapping"
    return type(value).__name__


def _repeated_type_mismatch(tests: list[Mapping[str, Any]]) -> bool:
    pairs: Counter[tuple[str, str]] = Counter()
    for test in tests:
        if test.get("passed") or test.get("status") != "wrong_answer":
            continue
        if "expected_output" not in test or "actual_output" not in test:
            continue
        expected = _type_family(test["expected_output"])
        actual = _type_family(test["actual_output"])
        if expected != actual:
            pairs[(expected, actual)] += 1
    return any(count >= 2 for count in pairs.values())


def classify_failure_mode(
    result: Mapping[str, Any], problem: Mapping[str, Any] | None = None
) -> FailureClassification | None:
    """Classify a terminal result, abstaining from unsupported causal guesses.

    ``problem`` may provide visible test inputs for the boundary rule. Hidden
    inputs are never inspected; hidden test IDs may provide an explicit label.
    """
    if result.get("evaluation_completed") is False or result.get("status") in _NON_FAILURE_STATUSES:
        return None

    sandbox, stage = _active_sandbox(result)
    tests = _as_tests(sandbox)
    messages = _messages(result, sandbox, tests)

    iterations = result.get("iterations")
    last_iteration = (
        _as_mapping(iterations[-1]) if isinstance(iterations, list) and iterations else {}
    )
    if result.get("failure_category") == "model_error" or last_iteration.get("llm_error"):
        return FailureClassification("infrastructure_error", 0.92, ("harness:model_error",))

    if _has_status(sandbox, tests, "syntax_error"):
        return FailureClassification("syntax_error", 0.99, ("sandbox:syntax_error",))
    if _has_status(sandbox, tests, "timeout"):
        return FailureClassification("timeout", 0.99, ("sandbox:timeout",))

    if _has_status(sandbox, tests, "backend_unavailable"):
        return FailureClassification("infrastructure_error", 0.99, ("sandbox:backend_unavailable",))
    if _has_status(sandbox, tests, "sandbox_error"):
        return FailureClassification("infrastructure_error", 0.96, ("sandbox:sandbox_error",))

    if any(_SYNTAX_EXCEPTIONS.search(message) for message in messages):
        return FailureClassification("syntax_error", 0.93, ("message:syntax_exception",))
    if any(_TIMEOUT_MESSAGE.search(message) for message in messages):
        return FailureClassification("timeout", 0.91, ("message:timeout",))

    if any(_CONTRACT_MESSAGE.search(message) for message in messages):
        return FailureClassification("understanding_error", 0.94, ("message:contract_mismatch",))

    if _repeated_type_mismatch(tests):
        return FailureClassification(
            "understanding_error", 0.84, ("failed_cases:repeated_output_type_mismatch",)
        )

    boundary = _boundary_evidence(tests, messages, problem, stage)
    if boundary is not None:
        return boundary

    if _has_status(sandbox, tests, "runtime_error") or _has_status(sandbox, tests, "memory_error"):
        return FailureClassification("runtime_error", 0.97, ("sandbox:runtime_error",))
    if any(_RUNTIME_EXCEPTIONS.search(message) for message in messages):
        return FailureClassification("runtime_error", 0.86, ("message:runtime_exception",))
    if any(_INFRA_MESSAGE.search(message) for message in messages):
        return FailureClassification("infrastructure_error", 0.90, ("message:infrastructure",))

    if result.get("failure_category") == "wrong_answer" or any(
        test.get("status") == "wrong_answer" for test in tests if not test.get("passed")
    ):
        return FailureClassification("logic_error", 0.78, ("sandbox:wrong_answer",))

    return FailureClassification("unknown", 0.30, ("failure:insufficient_evidence",))
