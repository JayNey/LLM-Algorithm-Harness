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
from collections.abc import Iterable, Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from src.budget import BudgetExhausted
from src.models import LLMResponse
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
                f"Unknown strategy in difficulty-strategy mapping: {', '.join(unknown_strategies)}"
            )
        if not mapping:
            raise ValueError("difficulty-strategy mapping must not be empty")
        self.mapping = dict(mapping)

    def select(self, difficulty: str | None) -> str:
        """Return the strategy for a difficulty; uncovered difficulties fail fast."""
        strategy = self.mapping.get(difficulty or "")
        if strategy is None:
            raise ValueError(
                f"Difficulty '{difficulty}' is not covered by the difficulty-strategy mapping"
            )
        return strategy

    def validate_coverage(self, difficulties: Iterable[str | None]) -> None:
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


UNKNOWN_COST_BUDGET = "Evaluation paused because some model costs are unknown"
MISSING_PRICING_BUDGET = "Evaluation paused because the configured model has no pricing"
REACHED_COST_BUDGET = "Evaluation cost budget exhausted"


def priced_amount(pricing: Mapping[str, Any] | None) -> Decimal | None:
    """Read a known USD amount, including an explicitly priced zero."""
    if not pricing or pricing.get("usage_known") is False or pricing.get("pricing_known") is False:
        return None
    if pricing.get("source") == "unknown":
        return None
    try:
        amount = Decimal(str(pricing.get("total_cost")))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def result_cost_details(result: Any) -> tuple[Decimal, bool, bool]:
    """Return known subtotal, whether any amount is known, and completeness flag."""
    metadata = getattr(result, "metadata", None) or {}
    if "cost_known" in metadata:
        return (
            Decimal(str(metadata["cost_usd"])),
            bool(metadata["cost_known"]),
            bool(metadata.get("cost_unknown")),
        )

    total = Decimal(0)
    known = False
    traces = getattr(result, "llm_traces", None) or []
    unknown = bool(
        metadata.get("cost_unknown") or (not traces and getattr(result, "total_tokens", 0))
    )
    for trace in traces:
        pricing = trace.get("pricing_metadata") if isinstance(trace, dict) else None
        amount = priced_amount(pricing if isinstance(pricing, dict) else None)
        if amount is None:
            unknown = True
        else:
            total += amount
            known = True
    return total, known, unknown


def result_cost(result: Any) -> tuple[Decimal, bool]:
    """Known subtotal and whether any call cost is unknown."""
    total, _, unknown = result_cost_details(result)
    return total, unknown


class UnitCallCost:
    """Track actual requests, including SDK failures that never produce a trace."""

    def __init__(self) -> None:
        self.events: set[str] = set()
        self.known_cost = Decimal(0)
        self.has_known_cost = False
        self.unknown = False

    def observe(self, event_id: str, response: LLMResponse | None, cached: bool) -> None:
        if event_id in self.events:
            return
        self.events.add(event_id)
        if cached:
            return
        amount = (
            priced_amount(response.pricing_metadata)
            if response is not None and not response.usage_missing
            else None
        )
        if amount is None:
            self.unknown = True
        else:
            self.known_cost += amount
            self.has_known_cost = True

    def check_unknown(self) -> None:
        if self.unknown:
            raise BudgetExhausted(UNKNOWN_COST_BUDGET)

    def write_result(self, result: Any) -> None:
        if self.events:
            result.metadata.update(
                cost_usd=float(self.known_cost),
                cost_known=self.has_known_cost,
                cost_unknown=self.unknown,
            )


class RunCostMonitor:
    """Thread-safe run-level cost ledger driving the budget-cap downgrade."""

    def __init__(self, budget_cap_usd: float | None = None):
        self.budget_cap_usd = Decimal(str(budget_cap_usd)) if budget_cap_usd is not None else None
        self._lock = threading.Lock()
        self._accumulated_cost = Decimal("0")
        self._unknown_usage_results = 0
        self._has_known_cost = False
        self.missing_pricing = False
        self._downgraded_count = 0

    def add_result(self, result: Any) -> None:
        """Settle one finished problem's known-pricing cost into the ledger."""
        known_cost, has_known_cost, usage_unknown = result_cost_details(result)
        with self._lock:
            self._accumulated_cost += known_cost
            self._has_known_cost |= has_known_cost
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
    def unknown_cost_blocks_dispatch(self) -> bool:
        with self._lock:
            return self.budget_cap_usd is not None and (
                self.missing_pricing or self._unknown_usage_results > 0
            )

    def _budget_status(self) -> str:
        if self.budget_cap_usd is None:
            return "unlimited"
        if self.missing_pricing:
            return "missing_pricing"
        if self._unknown_usage_results:
            return "unknown_cost"
        if self._accumulated_cost >= self.budget_cap_usd:
            return "reached"
        return "within_limit"

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
                "known_cost_usd": (
                    float(self._accumulated_cost)
                    if self._has_known_cost
                    or not (self._unknown_usage_results or self.missing_pricing)
                    else None
                ),
                "budget_status": self._budget_status(),
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
