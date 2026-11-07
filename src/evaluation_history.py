"""Outcome rules for historical practice evaluations."""

from collections.abc import Mapping
from typing import Any

_UNEVALUATED_STATUSES = {"budget_exhausted", "unsupported", "cancelled", "canceled"}


def is_completed_evaluation(record: Mapping[str, Any]) -> bool:
    """Check the recorded outcome, including legacy rows without a completion flag."""
    status = record.get("status")
    return (
        isinstance(status, str)
        and bool(status)
        and status not in _UNEVALUATED_STATUSES
        and record.get("evaluation_completed") is not False
    )


def is_solved_evaluation(record: Mapping[str, Any]) -> bool:
    """A completed evaluation is solved if public and any hidden tests passed."""
    if record.get("status") != "success":
        return False
    hidden = record.get("hidden_result")
    return not hidden or bool(hidden.get("all_passed", False))
