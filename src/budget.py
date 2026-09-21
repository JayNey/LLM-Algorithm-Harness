"""
Budget primitives for fixed-budget experiments (issue #15).

A BudgetTracker enforces per-problem call/token/time caps. The harness owns
one tracker per model x strategy x repeat combination and points it at the
problem being executed; a BudgetedLLMClient wraps the real client so every
strategy call path is gated without touching strategy code.

Token budgets settle against known provider usage only. A provider response
without usage data cannot satisfy a strict token budget, so the combination
is flagged ``token_budget_unsupported`` instead of pretending enforcement.
"""

import time
from typing import Any, Dict, Optional

from src.models import ProblemBudget
from src.utils.logging import get_logger

logger = get_logger(__name__)

STOP_COMPLETED = "completed"
STOP_MAX_CALLS = "budget_exhausted: max_calls"
STOP_MAX_TOKENS = "budget_exhausted: max_tokens"
STOP_MAX_SECONDS = "budget_exhausted: max_seconds"


class BudgetExhausted(Exception):
    """Raised before a model call when the problem's budget cannot cover it."""


class BudgetTracker:
    """Per-problem budget ledger and gate for one experiment combination."""

    def __init__(self, budget: Optional[ProblemBudget] = None):
        self.budget = budget
        self.current_problem: Optional[str] = None
        self.ledger: Dict[str, Dict[str, Any]] = {}
        self.token_budget_unsupported = False
        self._problem_started: Optional[float] = None

    def begin_problem(self, problem_id: str) -> None:
        """Start a fresh budget window for a problem."""
        self.current_problem = problem_id
        self._problem_started = time.monotonic()
        self.ledger[problem_id] = {
            "problem_id": problem_id,
            "calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "reasoning_tokens": 0,
            "total_tokens": 0,
            "elapsed_seconds": 0.0,
            "usage_missing_seen": False,
            "stop_reason": None,
        }

    def _entry(self) -> Optional[Dict[str, Any]]:
        if self.current_problem is None:
            return None
        return self.ledger.get(self.current_problem)

    def allow_call(self) -> bool:
        """Whether the current problem's budget still covers another call."""
        entry = self._entry()
        if entry is None or self.budget is None:
            return True
        if self.budget.max_calls is not None and entry["calls"] >= self.budget.max_calls:
            entry["stop_reason"] = STOP_MAX_CALLS
            return False
        if self.budget.max_tokens is not None and entry["total_tokens"] >= self.budget.max_tokens:
            entry["stop_reason"] = STOP_MAX_TOKENS
            return False
        if self.budget.max_seconds is not None and self._problem_started is not None:
            if time.monotonic() - self._problem_started >= self.budget.max_seconds:
                entry["stop_reason"] = STOP_MAX_SECONDS
                return False
        return True

    def stop_reason(self) -> str:
        """The recorded stop reason for the current problem."""
        entry = self._entry()
        return entry["stop_reason"] if entry else "budget_exhausted"

    def record(self, response: Any) -> None:
        """Settle one completed model call against the current problem."""
        entry = self._entry()
        if entry is None:
            return
        usage = getattr(response, "usage", None)
        entry["calls"] += 1
        if usage is not None:
            entry["prompt_tokens"] += getattr(usage, "prompt_tokens", 0) or 0
            entry["completion_tokens"] += getattr(usage, "completion_tokens", 0) or 0
            entry["reasoning_tokens"] += getattr(usage, "reasoning_tokens", 0) or 0
            entry["total_tokens"] += getattr(usage, "total_tokens", 0) or 0
        if getattr(response, "usage_missing", False):
            entry["usage_missing_seen"] = True
            if self.budget is not None and self.budget.max_tokens is not None:
                self.token_budget_unsupported = True
                logger.warning(
                    "token_budget_unsupported",
                    problem=self.current_problem,
                    detail="provider returned no usage data; strict token budget cannot be enforced",
                )

    def finalize_problem(self) -> None:
        """Close the current problem's budget window."""
        entry = self._entry()
        if entry is None:
            return
        if self._problem_started is not None:
            entry["elapsed_seconds"] = time.monotonic() - self._problem_started
        if entry["stop_reason"] is None:
            entry["stop_reason"] = STOP_COMPLETED


class BudgetedLLMClient:
    """Wrap an LLM client so every generate call is budget-gated and recorded."""

    def __init__(self, inner: Any, tracker: BudgetTracker):
        self._inner = inner
        self._tracker = tracker

    def generate(self, *args: Any, **kwargs: Any):
        if not self._tracker.allow_call():
            raise BudgetExhausted(self._tracker.stop_reason())
        response = self._inner.generate(*args, **kwargs)
        self._tracker.record(response)
        return response

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)
