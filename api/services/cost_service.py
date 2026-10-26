"""Cost tracking, budget and pricing service (issue #154).

Cost figures are read-only aggregations over the existing job tables —
this service never writes spend records. Budgets, alert rules, alert
events and pricing overrides are new owner-scoped tables.
"""

import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.config import settings
from api.db import (
    ABTest,
    AlertEvent,
    AlertRule,
    BenchmarkRun,
    Budget,
    Evaluation,
    EvaluationResult,
    Experiment,
    PricingOverride,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.engine import business_database_url
from api.db.models import utcnow
from src.cost_optimizer import build_advisory
from src.utils.pricing import PricingManager

_CHANNELS = frozenset({"slack", "webhook", "smtp", "log"})
_JOB_SOURCES = ("evaluations", "experiments", "benchmarks", "ab_tests")


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _mask_target(target: str) -> str:
    """Keep scheme and host; mask everything that can carry credentials."""
    if "://" in target:
        scheme, rest = target.split("://", 1)
        authority = rest.split("/", 1)[0].split("@")[-1]
        host = authority.split("?", 1)[0].split("#", 1)[0]
        return f"{scheme}://{host}/***"
    if "@" in target:
        _, domain = target.rsplit("@", 1)
        return f"***@{domain}"
    return "***"


class CostService:
    """Cost queries, budget config, alert rules and pricing overrides."""

    def __init__(self, database_url: str | None = None):
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)

    def _session(self) -> Session:
        return self._session_factory()

    # -- period parsing ------------------------------------------------------

    @staticmethod
    def _period(since: str | None, until: str | None) -> tuple[datetime | None, datetime | None]:
        """Parse ISO period bounds; date-only bounds cover the entire day."""

        def parse(raw: str | None, *, end: bool = False) -> datetime | None:
            if raw is None:
                return None
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
                day = date.fromisoformat(raw)
                return datetime.combine(day, datetime.max.time() if end else datetime.min.time())
            try:
                parsed = datetime.fromisoformat(raw)
            except ValueError:
                raise ValueError(f"invalid ISO timestamp: {raw}") from None
            if parsed.tzinfo is not None:
                parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed

        start = parse(since)
        end = parse(until, end=True)
        if start and end and start > end:
            raise ValueError("since must not be after until")
        return start, end

    def _spend_rows(
        self, owner_id: str, start: datetime | None, end: datetime | None
    ) -> list[dict[str, Any]]:
        """Unified spend records from evaluations and benchmark runs."""
        rows: list[dict[str, Any]] = []
        with self._session() as session:
            evaluations = session.scalars(
                select(Evaluation).where(Evaluation.user_id == owner_id)
            ).all()
            for row in evaluations:
                if not row.spent_usd:
                    continue
                rows.append(
                    {
                        "timestamp": row.created_at,
                        "cost_usd": row.spent_usd,
                        "source": "evaluations",
                        "task_id": row.id,
                        "model": row.model or "evaluation-run",
                        "strategies": list(row.strategy_names or []),
                        "problem_ids": list(row.problem_ids or []),
                        "completed": row.completed_count,
                    }
                )
            runs = session.scalars(
                select(BenchmarkRun).where(
                    BenchmarkRun.user_id == owner_id,
                    BenchmarkRun.status == "completed",
                )
            ).all()
            for run in runs:
                if run.cost_usd is None:
                    continue
                rows.append(
                    {
                        "timestamp": run.completed_at or run.created_at,
                        "cost_usd": run.cost_usd,
                        "source": "benchmarks",
                        "task_id": run.id,
                        "model": run.model,
                        "strategies": [],
                        "problem_ids": [],
                        "completed": 0,
                    }
                )
        if start:
            rows = [r for r in rows if r["timestamp"] and r["timestamp"] >= start]
        if end:
            rows = [r for r in rows if r["timestamp"] and r["timestamp"] <= end]
        return rows

    # -- task cost -----------------------------------------------------------

    def task_cost(self, task_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            evaluation = session.get(Evaluation, task_id)
            if evaluation and evaluation.user_id == owner_id:
                return {
                    "task_id": task_id,
                    "source": "evaluations",
                    "status": evaluation.status,
                    "total_cost_usd": evaluation.spent_usd,
                    "budget_cap_usd": evaluation.budget_cap_usd,
                    "problem_count": evaluation.problem_count,
                }
            run = session.get(BenchmarkRun, task_id)
            if run and run.user_id == owner_id:
                return {
                    "task_id": task_id,
                    "source": "benchmarks",
                    "status": run.status,
                    "total_cost_usd": run.cost_usd,
                    "budget_cap_usd": None,
                    "model": run.model,
                    "accuracy": run.accuracy,
                }
            experiment = session.get(Experiment, task_id)
            if experiment and experiment.user_id == owner_id:
                return {
                    "task_id": task_id,
                    "source": "experiments",
                    "status": experiment.status,
                    "total_cost_usd": None,
                    "budget_cap_usd": None,
                }
            ab_test = session.get(ABTest, task_id)
            if ab_test and ab_test.user_id == owner_id:
                return {
                    "task_id": task_id,
                    "source": "ab_tests",
                    "status": ab_test.status,
                    "total_cost_usd": None,
                    "budget_cap_usd": None,
                }
        raise ValueError(f"Task {task_id} not found")

    # -- aggregates ----------------------------------------------------------

    def summary(self, owner_id: str, since: str | None, until: str | None) -> dict[str, Any]:
        start, end = self._period(since, until)
        rows = self._spend_rows(owner_id, start, end)
        by_source: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        total = 0.0
        for row in rows:
            by_source[row["source"]] += row["cost_usd"]
            counts[row["source"]] += 1
            total += row["cost_usd"]
        return {
            "since": since,
            "until": until,
            "total_cost_usd": round(total, 6),
            "task_count": len(rows),
            "by_source": {
                source: {"cost_usd": round(amount, 6), "task_count": counts[source]}
                for source, amount in by_source.items()
            },
        }

    def trends(self, owner_id: str, since: str | None, until: str | None) -> dict[str, Any]:
        start, end = self._period(since, until)
        rows = self._spend_rows(owner_id, start, end)
        daily: dict[str, float] = defaultdict(float)
        for row in rows:
            if row["timestamp"]:
                day = row["timestamp"].date().isoformat()
                daily[day] += row["cost_usd"]
        series = [{"date": day, "cost_usd": round(daily[day], 6)} for day in sorted(daily)]
        return {"since": since, "until": until, "data": series}

    def breakdown(self, owner_id: str, since: str | None, until: str | None) -> dict[str, Any]:
        start, end = self._period(since, until)
        rows = self._spend_rows(owner_id, start, end)
        by_source: dict[str, float] = defaultdict(float)
        by_model: dict[str, float] = defaultdict(float)
        by_strategy: dict[str, float] = defaultdict(float)
        for row in rows:
            by_source[row["source"]] += row["cost_usd"]
            by_model[row["model"]] += row["cost_usd"]
            strategies = row["strategies"] or ["unknown"]
            share = row["cost_usd"] / len(strategies)
            for strategy in strategies:
                by_strategy[strategy] += share
        return {
            "since": since,
            "until": until,
            "by_source": {k: round(v, 6) for k, v in by_source.items()},
            "by_model": {k: round(v, 6) for k, v in by_model.items()},
            "by_strategy": {k: round(v, 6) for k, v in by_strategy.items()},
        }

    # -- budgets -------------------------------------------------------------

    @staticmethod
    def execution_budget(session: Session, owner_id: str) -> dict[str, Any] | None:
        """Fresh personal limits at a dispatch boundary, using persisted known costs.

        Global spend matches the cost API. Difficulty spend uses result costs,
        rather than the proportional estimate exposed by ``budget_usage``.
        The caller owns the session and must call this on its orchestration thread.
        """
        budget = session.scalar(
            select(Budget)
            .where(Budget.user_id == owner_id)
            .execution_options(populate_existing=True)
        )
        if budget is None:
            return None
        evaluation_costs = session.scalars(
            select(Evaluation.spent_usd).where(Evaluation.user_id == owner_id)
        )
        used = sum((Decimal(str(cost or 0)) for cost in evaluation_costs), Decimal(0))
        benchmark_costs = session.scalars(
            select(BenchmarkRun.cost_usd).where(
                BenchmarkRun.user_id == owner_id, BenchmarkRun.status == "completed"
            )
        )
        used += sum((Decimal(str(cost or 0)) for cost in benchmark_costs), Decimal(0))
        difficulty_used: dict[str, Decimal] = defaultdict(Decimal)
        caps = budget.difficulty_caps or {}
        if caps:
            metrics_rows = session.scalars(
                select(EvaluationResult.metrics)
                .join(Evaluation, Evaluation.id == EvaluationResult.evaluation_id)
                .where(Evaluation.user_id == owner_id)
            )
            for metrics in metrics_rows:
                if metrics and metrics.get("difficulty") in caps:
                    difficulty_used[metrics["difficulty"]] += Decimal(
                        str(metrics.get("cost_usd") or 0)
                    )
        return {
            "global_cap_usd": budget.global_cap_usd,
            "used_usd": used,
            "action": budget.action,
            "global_reached": (
                budget.global_cap_usd is not None and used >= Decimal(str(budget.global_cap_usd))
            ),
            "exhausted_difficulties": [
                name for name, cap in caps.items() if difficulty_used[name] >= Decimal(str(cap))
            ],
        }

    def _budget_row(self, session: Session, owner_id: str) -> Budget | None:
        return session.scalar(select(Budget).where(Budget.user_id == owner_id))

    @staticmethod
    def _budget_view(row: Budget) -> dict[str, Any]:
        return {
            "global_cap_usd": row.global_cap_usd,
            "difficulty_caps": row.difficulty_caps,
            "action": row.action,
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def get_budget(self, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._budget_row(session, owner_id)
            return self._budget_view(row) if row else {}

    def upsert_budget(
        self, request: Any, owner_id: str, *, partial: bool = False
    ) -> dict[str, Any]:
        """Create or update the caller's budget; partial mode keeps unset fields."""
        with self._session() as session, session.begin():
            row = self._budget_row(session, owner_id)
            if row is None:
                row = Budget(id=str(uuid.uuid4()), user_id=owner_id, created_at=utcnow())
                session.add(row)
                try:
                    session.flush()
                except IntegrityError:
                    raise ValueError("Budget already exists") from None
            if partial:
                # PATCH: unset fields keep their stored value; action is
                # optional in the request model, so None means "keep".
                if request.global_cap_usd is not None:
                    row.global_cap_usd = request.global_cap_usd
                if request.difficulty_caps is not None:
                    row.difficulty_caps = request.difficulty_caps
                if request.action is not None:
                    row.action = request.action
            else:
                # POST: full replace; a missing action defaults to "pause".
                row.global_cap_usd = request.global_cap_usd
                row.difficulty_caps = request.difficulty_caps
                row.action = request.action or "pause"
            row.updated_at = utcnow()
            return self._budget_view(row)

    def budget_usage(self, owner_id: str) -> dict[str, Any]:
        rows = self._spend_rows(owner_id, None, None)
        used = sum(row["cost_usd"] for row in rows)

        with self._session() as session:
            budget = self._budget_row(session, owner_id)
        global_section: dict[str, Any] = {
            "cap_usd": budget.global_cap_usd if budget else None,
            "used_usd": round(used, 6),
            "remaining_usd": (
                round(budget.global_cap_usd - used, 6)
                if budget and budget.global_cap_usd is not None
                else None
            ),
            "percentage_used": (
                round(used / budget.global_cap_usd * 100, 2)
                if budget and budget.global_cap_usd
                else None
            ),
        }

        # Per-difficulty usage is an estimate: each evaluation's spend is
        # spread evenly across the known difficulties of its problem ids.
        with self._session() as session:
            from api.db.models import Problem

            problems = {
                problem.problem_id: problem.difficulty
                for problem in session.scalars(select(Problem)).all()
            }
        difficulty_used: dict[str, float] = defaultdict(float)
        for row in rows:
            if row["source"] != "evaluations" or not row["problem_ids"]:
                continue
            difficulties = [
                name for name in (problems.get(pid) for pid in row["problem_ids"]) if name
            ]
            if not difficulties:
                continue
            share = row["cost_usd"] / len(difficulties)
            for difficulty in difficulties:
                difficulty_used[difficulty] += share

        caps: dict[str, Any] = (budget.difficulty_caps if budget else None) or {}
        by_difficulty = {
            difficulty: {
                "cap_usd": caps.get(difficulty),
                "used_usd": round(difficulty_used.get(difficulty, 0.0), 6),
                "percentage_used": (
                    round(difficulty_used.get(difficulty, 0.0) / caps[difficulty] * 100, 2)
                    if caps.get(difficulty)
                    else None
                ),
            }
            for difficulty in ("easy", "medium", "hard")
        }
        return {
            "global_budget": global_section,
            "by_difficulty": by_difficulty,
            "basis": (
                "per-difficulty used is an estimate: evaluation spend is spread "
                "evenly across difficulties of its known problem ids"
            ),
        }

    # -- alert rules ---------------------------------------------------------

    @staticmethod
    def _rule_view(row: AlertRule) -> dict[str, Any]:
        return {
            "id": row.id,
            "name": row.name,
            "threshold_pct": row.threshold_pct,
            "channel": row.channel,
            "target": _mask_target(row.target) if row.target else "",
            "enabled": bool(row.enabled),
            "created_at": _iso(row.created_at),
            "updated_at": _iso(row.updated_at),
        }

    def create_rule(self, request: Any, owner_id: str) -> dict[str, Any]:
        if not 1 <= request.threshold_pct <= 100:
            raise ValueError("threshold_pct must be between 1 and 100")
        if request.channel not in _CHANNELS:
            raise ValueError(f"channel must be one of {sorted(_CHANNELS)}")
        if request.channel != "log" and not request.target:
            raise ValueError(f"channel {request.channel} requires a target")
        row = AlertRule(
            id=str(uuid.uuid4()),
            user_id=owner_id,
            name=request.name,
            threshold_pct=request.threshold_pct,
            channel=request.channel,
            target=request.target,
            enabled=request.enabled,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self._session() as session, session.begin():
            session.add(row)
        return self._rule_view(row)

    def list_rules(self, owner_id: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(AlertRule)
                .where(AlertRule.user_id == owner_id)
                .order_by(AlertRule.threshold_pct, AlertRule.id)
            ).all()
        return [self._rule_view(row) for row in rows]

    def _owned_rule(self, session: Session, rule_id: str, owner_id: str) -> AlertRule:
        row = session.get(AlertRule, rule_id)
        if row is None or row.user_id != owner_id:
            raise ValueError(f"Alert rule {rule_id} not found")
        return row

    def update_rule(self, rule_id: str, request: Any, owner_id: str) -> dict[str, Any]:
        with self._session() as session, session.begin():
            row = self._owned_rule(session, rule_id, owner_id)
            if request.threshold_pct is not None:
                if not 1 <= request.threshold_pct <= 100:
                    raise ValueError("threshold_pct must be between 1 and 100")
                row.threshold_pct = request.threshold_pct
            if request.channel is not None:
                if request.channel not in _CHANNELS:
                    raise ValueError(f"channel must be one of {sorted(_CHANNELS)}")
                row.channel = request.channel
            if request.target is not None:
                row.target = request.target
            if request.enabled is not None:
                row.enabled = request.enabled
            if request.name is not None:
                row.name = request.name
            if row.channel != "log" and not row.target:
                raise ValueError(f"channel {row.channel} requires a target")
            row.updated_at = utcnow()
            return self._rule_view(row)

    def delete_rule(self, rule_id: str, owner_id: str) -> None:
        with self._session() as session, session.begin():
            row = self._owned_rule(session, rule_id, owner_id)
            session.delete(row)

    def alert_history(self, owner_id: str, limit: int = 50) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(AlertEvent)
                .where(AlertEvent.user_id == owner_id, AlertEvent.channel != "pending")
                .order_by(AlertEvent.created_at.desc())
                .limit(limit)
            ).all()
        return [
            {
                "id": row.id,
                "rule_id": row.rule_id,
                "threshold_pct": row.threshold_pct,
                "used_usd": row.used_usd,
                "cap_usd": row.cap_usd,
                "channel": row.channel,
                "triggered_at": _iso(row.created_at),
            }
            for row in rows
        ]

    # -- pricing -------------------------------------------------------------

    def pricing_catalog(self) -> dict[str, Any]:
        manager = PricingManager()
        catalog: dict[str, Any] = {}
        for model, entry in manager.BUILTIN_PRICING.items():
            catalog[model] = {
                "prompt_per_1k": entry["prompt"],
                "completion_per_1k": entry["completion"],
                "source": "builtin",
            }
        for model, entry in manager.custom_pricing.items():
            catalog[model] = {
                "prompt_per_1k": entry["prompt"],
                "completion_per_1k": entry["completion"],
                "source": "custom_file",
            }
        with self._session() as session:
            rows = session.scalars(
                select(PricingOverride).order_by(PricingOverride.created_at)
            ).all()
        for row in rows:
            catalog[row.model] = {
                "prompt_per_1k": row.prompt_per_1k,
                "completion_per_1k": row.completion_per_1k,
                "source": "override",
            }
        return {"models": catalog}

    def pricing_history(self, model: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(PricingOverride)
                .where(PricingOverride.model == model)
                .order_by(PricingOverride.created_at.desc())
            ).all()
        return [
            {
                "prompt_per_1k": row.prompt_per_1k,
                "completion_per_1k": row.completion_per_1k,
                "created_by": row.created_by,
                "created_at": _iso(row.created_at),
            }
            for row in rows
        ]

    def set_pricing_override(self, model: str, request: Any, owner_id: str) -> dict[str, Any]:
        row = PricingOverride(
            id=str(uuid.uuid4()),
            model=model,
            prompt_per_1k=request.prompt_per_1k,
            completion_per_1k=request.completion_per_1k,
            created_by=owner_id,
            created_at=utcnow(),
        )
        with self._session() as session, session.begin():
            session.add(row)
        return {
            "model": row.model,
            "prompt_per_1k": row.prompt_per_1k,
            "completion_per_1k": row.completion_per_1k,
            "created_at": _iso(row.created_at),
        }

    # -- reports -------------------------------------------------------------

    def task_report(self, task_id: str, owner_id: str) -> dict[str, Any]:
        task = self.task_cost(task_id, owner_id)
        total = task.get("total_cost_usd")
        cap = task.get("budget_cap_usd")
        task["percentage_used"] = round(total / cap * 100, 2) if total is not None and cap else None
        task["pricing_metadata"] = {
            "source": "business_db",
            "data_root": str(settings.DATA_ROOT),
        }
        return task

    def cost_optimization_report(self, owner_id: str) -> dict[str, Any]:
        """Synthesize a comparison from the user's own runs and advise on it.

        Accuracy uses the ``pass_rate_over_total`` key that
        ``build_advisory``/``_accuracy`` read; benchmark accuracy and cost
        are aggregated in a single pass over completed runs so the ratio
        denominator cannot diverge from the accuracy sample.
        """
        by_model: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"accuracy_sum": 0.0, "count": 0, "cost": 0.0}
        )
        evaluations: dict[tuple[str, str], dict[str, Any]] = defaultdict(
            lambda: {"accuracy_sum": 0.0, "count": 0, "cost": 0.0, "solved": 0}
        )

        with self._session() as session:
            runs = session.scalars(
                select(BenchmarkRun).where(
                    BenchmarkRun.user_id == owner_id,
                    BenchmarkRun.status == "completed",
                )
            ).all()
            rows = session.scalars(
                select(Evaluation).where(
                    Evaluation.user_id == owner_id,
                    Evaluation.status == "completed",
                )
            ).all()

        for run in runs:
            if not run.model:
                continue
            bucket = by_model[run.model]
            bucket["count"] += 1
            if run.accuracy is not None:
                bucket["accuracy_sum"] += run.accuracy
            bucket["cost"] += run.cost_usd or 0.0

        combos: list[dict[str, Any]] = []
        for model, bucket in by_model.items():
            accuracy = bucket["accuracy_sum"] / bucket["count"] if bucket["count"] else None
            combos.append(
                {
                    "model": model,
                    "strategy": "benchmark",
                    "solved": round((accuracy or 0.0) * 100),
                    "pass_rate_over_total": accuracy,
                    "cost": {"known": True, "total_cost_usd": round(bucket["cost"], 6)},
                }
            )

        for evaluation in rows:
            if not evaluation.strategy_names or evaluation.problem_count == 0:
                continue
            key = (evaluation.model or "evaluation-run", "+".join(evaluation.strategy_names))
            bucket = evaluations[key]
            bucket["count"] += 1
            bucket["accuracy_sum"] += evaluation.completed_count / evaluation.problem_count
            bucket["cost"] += evaluation.spent_usd or 0.0
            bucket["solved"] += evaluation.completed_count

        for (model, strategy), bucket in evaluations.items():
            accuracy = bucket["accuracy_sum"] / bucket["count"] if bucket["count"] else None
            combos.append(
                {
                    "model": model,
                    "strategy": strategy,
                    "solved": bucket["solved"],
                    "pass_rate_over_total": accuracy,
                    "cost": {"known": True, "total_cost_usd": round(bucket["cost"], 6)},
                }
            )

        comparison = {
            "experiment": {"experiment_id": f"user-{owner_id[:8]}"},
            "combinations": combos,
        }
        return build_advisory(comparison)
