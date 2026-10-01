"""
Cost-sensitive strategy selection and run-level budget downgrade (issue #56b).

CostAwareSelector maps each problem's dataset difficulty to a configured
strategy. RunCostMonitor accumulates known-pricing call cost across one run
and tells the harness when the budget cap is reached, so remaining problems
are downgraded to the cheapest mapped strategy.

Cost accounting mirrors ``harness._estimate_cost``: only traces with known
pricing and known usage count toward the accumulated total. Results with
unknown usage are counted separately and never treated as free.
"""

import threading
from decimal import Decimal, InvalidOperation
from typing import Any

from src.utils.logging import get_logger

logger = get_logger(__name__)

# Fixed cost ladder, most expensive first. The downgrade target for a
# mapping is the cheapest strategy that appears among its values.
STRATEGY_COST_LADDER = ["multi_round_feedback", "chain_of_thought", "vanilla"]
VALID_DIFFICULTIES = ("easy", "medium", "hard")


class CostAwareSelector:
    """Map dataset difficulty labels to strategy names."""

    def __init__(self, mapping: dict[str, str], allowed_strategies: list[str]):
        invalid_difficulties = sorted(set(mapping) - set(VALID_DIFFICULTIES))
        if invalid_difficulties:
            raise ValueError(
                "Unknown difficulty in difficulty-strategy mapping: "
                f"{', '.join(invalid_difficulties)}"
            )
        unknown_strategies = sorted(set(mapping.values()) - set(allowed_strategies))
        if unknown_strategies:
            raise ValueError(
                "Unknown strategy in difficulty-strategy mapping: "
                f"{', '.join(unknown_strategies)}"
            )
        if not mapping:
            raise ValueError("difficulty-strategy mapping must not be empty")
        self.mapping = dict(mapping)

    def select(self, difficulty: str | None) -> str:
        """Return the strategy for a difficulty; uncovered difficulties fail fast."""
        strategy = self.mapping.get(difficulty or "")
        if strategy is None:
            raise ValueError(
                f"Difficulty '{difficulty}' is not covered by the " "difficulty-strategy mapping"
            )
        return strategy

    def validate_coverage(self, difficulties) -> None:
        """Ensure every difficulty in the dataset has a mapping."""
        uncovered = sorted({str(d) for d in difficulties if (d or "") not in self.mapping})
        if uncovered:
            raise ValueError(
                "Difficulties present in the dataset are not covered by the "
                f"difficulty-strategy mapping: {', '.join(uncovered)}"
            )

    @property
    def cheapest_strategy(self) -> str:
        """The cheapest strategy among mapped values (downgrade target)."""
        present = set(self.mapping.values())
        for name in reversed(STRATEGY_COST_LADDER):
            if name in present:
                return name
        # Mapping values are constrained to the known strategies by the
        # constructor; the fallback only guards future custom strategy names.
        return sorted(present)[0]


def result_cost(result: Any) -> tuple[Decimal, bool]:
    """Known-pricing cost of one result, and whether its usage was unknown.

    Shared settlement logic for the run-level and per-difficulty ledgers and
    the report's per-difficulty cost breakdown. Mirrors
    ``harness._estimate_cost``: only traces with known pricing and known
    usage count toward the cost; unknown usage is flagged, never silently
    treated as free.
    """
    known_cost = Decimal("0")
    usage_unknown = False
    for trace in getattr(result, "llm_traces", None) or []:
        if not isinstance(trace, dict):
            usage_unknown = True
            continue
        pricing = trace.get("pricing_metadata")
        if not isinstance(pricing, dict):
            # Tokens without provider pricing cannot be converted honestly.
            usage_unknown = True
            continue
        trace_cost = pricing.get("total_cost")
        if (
            trace_cost is None
            or pricing.get("usage_known") is False
            or pricing.get("pricing_known") is False
        ):
            usage_unknown = True
        else:
            try:
                amount = Decimal(str(trace_cost))
            except (InvalidOperation, TypeError, ValueError):
                usage_unknown = True
                continue
            if not amount.is_finite() or amount < 0:
                usage_unknown = True
                continue
            known_cost += amount
    if not usage_unknown and not (getattr(result, "llm_traces", None) or []):
        # A result without traces still burns unpriced tokens when the
        # provider reported usage; truly call-free results stay clean.
        if getattr(result, "total_tokens", 0):
            usage_unknown = True
    return known_cost, usage_unknown


class RunCostMonitor:
    """Thread-safe run-level cost ledger driving the budget-cap downgrade."""

    def __init__(self, budget_cap_usd: float | None = None):
        self.budget_cap_usd = Decimal(str(budget_cap_usd)) if budget_cap_usd is not None else None
        self._lock = threading.Lock()
        self._accumulated_cost = Decimal("0")
        self._unknown_usage_results = 0
        self._downgraded_count = 0

    def add_result(self, result: Any) -> None:
        """Settle one finished problem's known-pricing cost into the ledger."""
        known_cost, usage_unknown = result_cost(result)
        with self._lock:
            self._accumulated_cost += known_cost
            if usage_unknown:
                self._unknown_usage_results += 1

    @property
    def over_cap(self) -> bool:
        """Whether the accumulated known cost has reached the budget cap."""
        if self.budget_cap_usd is None:
            return False
        with self._lock:
            return self._accumulated_cost >= self.budget_cap_usd

    @property
    def accumulated_cost(self) -> Decimal:
        """Exact known cost for threshold decisions, without display rounding."""
        with self._lock:
            return self._accumulated_cost

    def record_downgrade(self) -> bool:
        """Record one downgraded problem; True when this is the cap trigger."""
        with self._lock:
            first = self._downgraded_count == 0
            self._downgraded_count += 1
        return first

    def snapshot(self) -> dict[str, Any]:
        """Point-in-time view for logs and the run summary."""
        with self._lock:
            return {
                "budget_cap_usd": (
                    float(self.budget_cap_usd) if self.budget_cap_usd is not None else None
                ),
                "accumulated_cost_usd": float(round(self._accumulated_cost, 6)),
                "unknown_usage_results": self._unknown_usage_results,
                "downgraded_problems": self._downgraded_count,
            }


class DifficultyBudgetMonitor:
    """Per-difficulty budget ledgers; each difficulty degrades independently.

    Each configured difficulty gets its own RunCostMonitor with its budget
    as the cap. Problems of unconfigured difficulties are ignored here —
    they carry no per-difficulty budget and stay governed by the global cap.
    """

    def __init__(self, allocation: dict[str, float]):
        self.monitors = {difficulty: RunCostMonitor(cap) for difficulty, cap in allocation.items()}
        self._trigger_log_lock = threading.Lock()
        self._trigger_logged: set = set()

    def add_result(self, result: Any, difficulty: str | None) -> None:
        """Settle one finished problem into its difficulty's ledger."""
        monitor = self.monitors.get(difficulty or "")
        if monitor is not None:
            monitor.add_result(result)

    def over_cap_for(self, difficulty: str | None) -> bool:
        """Whether this difficulty has exhausted its own budget."""
        monitor = self.monitors.get(difficulty or "")
        return monitor.over_cap if monitor is not None else False

    def cap_for(self, difficulty: str | None) -> Decimal | None:
        """The configured budget for a difficulty, if any."""
        monitor = self.monitors.get(difficulty or "")
        return monitor.budget_cap_usd if monitor is not None else None

    def mark_trigger_logged(self, difficulty: str | None) -> bool:
        """True once per difficulty, so the budget trigger logs exactly once."""
        with self._trigger_log_lock:
            first = difficulty not in self._trigger_logged
            self._trigger_logged.add(difficulty)
        return first

    def record_downgrade(self, difficulty: str | None) -> bool:
        """Count one downgraded problem of this difficulty; True when first."""
        monitor = self.monitors.get(difficulty or "")
        return monitor.record_downgrade() if monitor is not None else False

    def snapshot(self) -> dict[str, dict[str, Any]]:
        """Per-difficulty budget usage for the run summary."""
        return {difficulty: monitor.snapshot() for difficulty, monitor in self.monitors.items()}
