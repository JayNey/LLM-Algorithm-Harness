"""Call-level accounting for experiments and A/B tests (#307).

No prompts, responses or credentials enter this store. Returned provider
usage and the contemporaneous pricing snapshot are the only cost evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.db.models import ABTest, Experiment, PricingOverride, SpendRecord
from src.models import LLMResponse
from src.utils.pricing import PricingInfo, PricingManager

SpendCallback = Callable[[str, LLMResponse | None, bool], None]
_SOURCES: dict[str, type[Experiment] | type[ABTest]] = {
    "experiments": Experiment,
    "ab_tests": ABTest,
}
_PRICING_FIELDS = (
    "model",
    "source",
    "as_of",
    "pricing_known",
    "usage_known",
    "total_cost",
    "prompt_price_per_1k",
    "completion_price_per_1k",
)


def pricing_snapshot(session_factory: Callable[[], Session]) -> PricingManager:
    """Use the same file/builtin/Web override precedence as evaluations."""
    manager = PricingManager()
    with session_factory() as session:
        for row in session.scalars(select(PricingOverride).order_by(PricingOverride.created_at)):
            manager.overrides[row.model] = PricingInfo(
                model=row.model,
                prompt_price=row.prompt_per_1k,
                completion_price=row.completion_per_1k,
                source="override",
                as_of=row.created_at.isoformat(),
            )
    return manager


def _amount(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


class SpendRecorder:
    def __init__(
        self, session_factory: Callable[[], Session], source: str, task_id: str, owner_id: str
    ):
        if source not in _SOURCES:
            raise ValueError("unsupported spend source")
        self.session_factory = session_factory
        self.source = source
        self.task_id = task_id
        self.owner_id = owner_id
        self._failed = Event()

    def check(self) -> None:
        """Prevent new provider requests after an accounting write failed."""
        if self._failed.is_set():
            raise RuntimeError("spend persistence unavailable; execution stopped")

    def callback(
        self,
        *,
        model: str,
        strategy: str,
        problem_id: str | None = None,
        difficulty: str | None = None,
    ) -> SpendCallback:
        def save(event_id: str, response: LLMResponse | None, cached: bool) -> None:
            try:
                self.record(
                    event_id,
                    response,
                    cached,
                    model=model,
                    strategy=strategy,
                    problem_id=problem_id,
                    difficulty=difficulty,
                )
            except Exception:
                self._failed.set()
                # Best effort: if the database recovers, never advertise full coverage.
                try:
                    with self.session_factory() as session, session.begin():
                        row = cast(
                            Experiment | ABTest | None,
                            session.get(_SOURCES[self.source], self.task_id),
                        )
                        if row is not None and row.user_id == self.owner_id:
                            row.cost_tracking_complete = False
                except Exception:
                    pass
                raise

        return save

    def record(
        self,
        event_id: str,
        response: LLMResponse | None,
        cached: bool,
        *,
        model: str,
        strategy: str,
        problem_id: str | None,
        difficulty: str | None,
    ) -> None:
        pricing = response.pricing_metadata or {} if response is not None else {}
        reason = None
        cost = _amount(pricing.get("total_cost"))
        if cached:
            cost = 0.0
        elif response is None:
            reason = "missing_response"
        elif response.usage_missing or pricing.get("usage_known") is False:
            reason = "missing_usage"
        elif pricing.get("pricing_known") is False or pricing.get("source") == "unknown":
            reason = "missing_pricing"
        elif cost is None:
            reason = "missing_pricing"
        if reason is not None:
            cost = None
        row = SpendRecord(
            id=event_id,
            user_id=self.owner_id,
            source=self.source,
            task_id=self.task_id,
            model=response.model if response is not None else model,
            strategy=strategy,
            problem_id=problem_id,
            difficulty=difficulty,
            cost_usd=cost,
            unknown_reason=reason,
            cached=cached,
            usage=response.usage.model_dump() if response is not None else None,
            pricing={key: pricing[key] for key in _PRICING_FIELDS if key in pricing},
        )
        with self.session_factory() as session:
            task = cast(
                Experiment | ABTest | None, session.get(_SOURCES[self.source], self.task_id)
            )
            if task is None or task.user_id != self.owner_id:
                raise ValueError("spend task not found")
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                previous = session.get(SpendRecord, event_id)
                if previous is None or (previous.user_id, previous.source, previous.task_id) != (
                    self.owner_id,
                    self.source,
                    self.task_id,
                ):
                    raise


def backfill_spend(
    session_factory: Callable[[], Session], *, dry_run: bool = False
) -> dict[str, Any]:
    """Import explicit legacy experiment snapshots; never reprice token totals.

    Legacy A/B artifacts lack billing evidence and remain unknown. Jobs with
    live records are skipped because their snapshots may overlap those calls.
    The legacy coverage flag stays false even for successfully imported jobs.
    """
    inserted = 0
    skipped: dict[str, str] = {}
    with session_factory() as session, session.begin():
        jobs = session.scalars(
            select(Experiment).where(Experiment.cost_tracking_complete.is_(False))
        ).all()
        for job in jobs:
            existing = session.scalars(
                select(SpendRecord).where(
                    SpendRecord.source == "experiments",
                    SpendRecord.task_id == job.id,
                    SpendRecord.user_id == job.user_id,
                )
            ).all()
            if any((r.pricing or {}).get("origin") != "historical_snapshot" for r in existing):
                skipped[job.id] = "live_records_present"
                continue
            if not job.output_dir:
                skipped[job.id] = "missing_artifacts"
                continue
            root = Path(job.output_dir).resolve()
            try:
                evidence_found = False
                metadata = json.loads((root / "experiment.json").read_text(encoding="utf-8"))
                if not isinstance(metadata, dict) or not isinstance(
                    metadata.get("combinations"), list
                ):
                    raise ValueError("invalid combination metadata")
                for combo in metadata["combinations"]:
                    if not isinstance(combo, dict):
                        raise ValueError("invalid combination")
                    directory = (root / combo["combo_dir"]).resolve()
                    if not directory.is_relative_to(root):
                        raise ValueError("combination outside artifact root")
                    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
                    if not isinstance(summary, dict) or not isinstance(
                        summary.get(combo["strategy"]), dict
                    ):
                        raise ValueError("invalid strategy summary")
                    pricing = summary[combo["strategy"]].get("pricing_metadata") or {}
                    if not isinstance(pricing, dict):
                        raise ValueError("invalid pricing snapshot")
                    cost = _amount(pricing.get("total_cost"))
                    if not pricing.get("has_actual_pricing") or cost is None:
                        continue
                    evidence_found = True
                    event_id = str(
                        uuid.uuid5(
                            uuid.NAMESPACE_URL, f"spend:experiments:{job.id}:{combo['combo_id']}"
                        )
                    )
                    if session.get(SpendRecord, event_id) is not None:
                        continue
                    timestamp = job.completed_at or job.started_at or job.created_at
                    basis = "legacy_completed_at" if job.completed_at else "legacy_task_time"
                    if not dry_run:
                        session.add(
                            SpendRecord(
                                id=event_id,
                                user_id=job.user_id,
                                source="experiments",
                                task_id=job.id,
                                occurred_at=timestamp,
                                model=combo["model"],
                                strategy=combo["strategy"],
                                cost_usd=cost,
                                cached=False,
                                unknown_reason=(
                                    "historical_partial"
                                    if pricing.get("unknown_usage")
                                    or pricing.get("unknown_pricing")
                                    else None
                                ),
                                pricing={
                                    "origin": "historical_snapshot",
                                    "timestamp_basis": basis,
                                    "artifact": f"{combo['combo_dir']}/summary.json",
                                    **pricing,
                                },
                            )
                        )
                        session.flush()
                    inserted += 1
                if not evidence_found:
                    skipped[job.id] = "no_verifiable_cost"
            except (OSError, ValueError, KeyError, TypeError):
                skipped[job.id] = "unverifiable_artifacts"
        return {"inserted": inserted, "skipped": skipped, "dry_run": dry_run}


def main() -> None:
    """Run explicitly with: python -m api.services.spend_records --dry-run."""
    from api.db import business_database_url, make_engine, make_session_factory, run_migrations

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    engine = make_engine(business_database_url())
    try:
        run_migrations(engine)
        print(json.dumps(backfill_spend(make_session_factory(engine), dry_run=args.dry_run)))
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
