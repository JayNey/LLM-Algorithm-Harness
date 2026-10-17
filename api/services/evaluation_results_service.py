"""Owner-scoped queries over stored evaluation results.

Routes stay thin. This service resolves a run for its owner, aggregates every
unit in that run, and applies the list filters.
"""

from __future__ import annotations

from datetime import datetime

from alembic import command
from alembic.config import Config
from sqlalchemy import Text, and_, cast, exists, func, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from api.db import (
    Evaluation,
    EvaluationResult,
    Problem,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.engine import business_database_url
from api.db.migrate import SCRIPT_LOCATION

_SORT_COLUMNS = {
    "completed_at": Evaluation.completed_at,
    "created_at": Evaluation.created_at,
}


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat() + "Z"


def _num(metrics: dict | None, key: str) -> float | None:
    if not metrics or key not in metrics or metrics[key] is None:
        return None
    return float(metrics[key])


def _by_difficulty(items: list[EvaluationResult]) -> dict[str, dict[str, float | int]]:
    """Group one strategy by the difficulty saved on each unit."""
    grouped: dict[str, list[EvaluationResult]] = {}
    for row in items:
        difficulty = (row.metrics or {}).get("difficulty")
        if not difficulty:
            continue
        grouped.setdefault(str(difficulty), []).append(row)
    summary: dict[str, dict[str, float | int]] = {}
    for name, rows in grouped.items():
        solved = sum(1 for row in rows if row.status == "success")
        summary[name] = {
            "success_rate": solved / len(rows),
            "solved": solved,
            "total": len(rows),
        }
    return summary


def aggregate(rows: list[EvaluationResult]) -> list[dict]:
    """Summarize every unit of a run, grouped by strategy.

    Later analytics and comparison reuse this so a detail page and a chart
    cannot drift apart. Cost skips units flagged cost_unknown.
    """
    grouped: dict[str, list[EvaluationResult]] = {}
    for row in rows:
        grouped.setdefault(row.strategy_name, []).append(row)
    strategies = []
    for name, items in grouped.items():
        solved = sum(1 for row in items if row.status == "success")
        known_cost = [
            float((row.metrics or {}).get("cost_usd") or 0)
            for row in items
            if not (row.metrics or {}).get("cost_unknown")
        ]
        times = [
            value
            for row in items
            if (value := _num(row.metrics, "execution_time_seconds")) is not None
        ]
        tokens = [
            value for row in items if (value := _num(row.metrics, "total_tokens")) is not None
        ]
        strategies.append(
            {
                "name": name,
                "success_rate": solved / len(items) if items else 0.0,
                "total_problems": len(items),
                "solved_problems": solved,
                "avg_tokens": (sum(tokens) / len(tokens)) if tokens else 0.0,
                "estimated_cost_usd": sum(known_cost),
                "unknown_cost_count": sum(
                    1 for row in items if (row.metrics or {}).get("cost_unknown")
                ),
                "avg_execution_time": (sum(times) / len(times)) if times else 0.0,
                "by_difficulty": _by_difficulty(items),
            }
        )
    return strategies


def _problem_item(row: EvaluationResult) -> dict:
    """One stored unit. Missing iterations stay null instead of becoming 0."""
    metrics = row.metrics
    return {
        "problem_id": row.problem_id,
        "strategy": row.strategy_name,
        "status": row.status,
        "iterations": (
            None if metrics is None or "iterations" not in metrics else metrics["iterations"]
        ),
        "tokens": (metrics or {}).get("total_tokens"),
        "execution_time": (metrics or {}).get("execution_time_seconds"),
    }


def _json_array_contains(column, value: str):
    """Match a JSON string array element without interpolating the value into SQL."""
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return cast(column, Text).like(f'%"{escaped}"%', escape="\\")


def _matching_unit_exists(strategy: str | None, difficulty: str | None, tag: str | None):
    """Keep a run when at least one of its units matches the optional filters."""
    if strategy is None and difficulty is None and tag is None:
        return None
    stmt = select(EvaluationResult.id).where(EvaluationResult.evaluation_id == Evaluation.id)
    if strategy is not None:
        stmt = stmt.where(EvaluationResult.strategy_name == strategy)
    if difficulty is not None or tag is not None:
        stmt = stmt.outerjoin(Problem, Problem.problem_id == EvaluationResult.problem_id)
    if difficulty is not None:
        stored = EvaluationResult.metrics["difficulty"].as_string()
        stmt = stmt.where(
            or_(
                stored == difficulty,
                and_(stored.is_(None), Problem.difficulty == difficulty),
            )
        )
    if tag is not None:
        stmt = stmt.where(_json_array_contains(Problem.tags, tag))
    return exists(stmt)


def _stamp_create_all_schema(engine: Engine) -> None:
    """Record head on a database that already has the current tables.

    Service tests build the schema with ``create_all`` before constructing the
    service. Alembic would otherwise try to create those tables again.
    """
    inspector = inspect(engine)
    if not inspector.has_table("evaluations") or inspector.has_table("alembic_version"):
        return
    url = engine.url.render_as_string(hide_password=False)
    cfg = Config()
    cfg.set_main_option("script_location", str(SCRIPT_LOCATION))
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    with engine.begin() as connection:
        cfg.attributes["connection"] = connection
        command.stamp(cfg, "head")


class EvaluationResultsService:
    """Read evaluation results that belong to one user."""

    def __init__(self, database_url: str | None = None):
        self._engine = make_engine(database_url or business_database_url())
        _stamp_create_all_schema(self._engine)
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)

    def _session(self) -> Session:
        return self._session_factory()

    def _resolve(self, session: Session, owner_id: str, key: str) -> Evaluation:
        """Match this user's evaluation id first, then run id."""
        owned = select(Evaluation).where(Evaluation.user_id == owner_id)
        found = session.scalar(owned.where(Evaluation.id == key))
        if found is None:
            found = session.scalar(owned.where(Evaluation.run_id == key))
        if found is None:
            raise ValueError("Evaluation not found")
        return found

    def detail(self, owner_id: str, run_id: str, limit: int = 20, offset: int = 0) -> dict:
        """Return the full strategy summary plus one page of problem units."""
        offset = max(offset, 0)
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            rows = list(
                session.scalars(
                    select(EvaluationResult)
                    .where(EvaluationResult.evaluation_id == evaluation.id)
                    .order_by(EvaluationResult.created_at, EvaluationResult.id)
                ).all()
            )
            total = len(rows)
            page = rows[offset : offset + limit]
            return {
                "run_id": evaluation.run_id,
                "status": evaluation.status,
                "created_at": _iso(evaluation.created_at),
                "completed_at": _iso(evaluation.completed_at),
                "strategies": aggregate(rows),
                "problems": {
                    "items": [_problem_item(row) for row in page],
                    "total": total,
                    "limit": limit,
                    "offset": offset,
                    "has_more": offset + limit < total,
                },
            }

    def list_runs(
        self,
        owner_id: str,
        *,
        strategy: str | None,
        difficulty: str | None,
        tag: str | None,
        status: str | None,
        limit: int,
        offset: int,
        sort: str,
        order: str,
    ) -> tuple[list[dict], int]:
        """List one user's evaluations. Unit filters use an EXISTS subquery."""
        offset = max(offset, 0)
        column = _SORT_COLUMNS.get(sort, Evaluation.completed_at)
        descending = str(order).lower() != "asc"
        primary = column.desc() if descending else column.asc()
        tie = Evaluation.id.desc() if descending else Evaluation.id.asc()
        filters = [Evaluation.user_id == owner_id]
        if status is not None:
            filters.append(Evaluation.status == status)
        matched = _matching_unit_exists(strategy, difficulty, tag)
        if matched is not None:
            filters.append(matched)
        with self._session() as session:
            total = session.scalar(select(func.count()).select_from(Evaluation).where(*filters))
            rows = session.scalars(
                select(Evaluation)
                .where(*filters)
                .order_by(primary, tie)
                .offset(offset)
                .limit(limit)
            ).all()
            items = [
                {
                    "id": row.id,
                    "run_id": row.run_id,
                    "status": row.status,
                    "model": row.model,
                    "strategy_names": list(row.strategy_names or []),
                    "created_at": _iso(row.created_at),
                    "completed_at": _iso(row.completed_at),
                }
                for row in rows
            ]
        return items, int(total or 0)

    def problem_history(
        self,
        owner_id: str,
        problem_id: str,
        *,
        status: str | None,
        limit: int,
        offset: int,
    ) -> tuple[list[dict], int]:
        """Return this user's units for one problem."""
        offset = max(offset, 0)
        filters = [
            Evaluation.user_id == owner_id,
            EvaluationResult.problem_id == problem_id,
        ]
        if status is not None:
            filters.append(EvaluationResult.status == status)
        joined = (
            select(EvaluationResult, Evaluation)
            .join(Evaluation, Evaluation.id == EvaluationResult.evaluation_id)
            .where(*filters)
        )
        with self._session() as session:
            total = session.scalar(select(func.count()).select_from(joined.subquery()))
            pairs = session.execute(
                joined.order_by(EvaluationResult.created_at, EvaluationResult.id)
                .offset(offset)
                .limit(limit)
            ).all()
            items = []
            for row, evaluation in pairs:
                item = _problem_item(row)
                item["run_id"] = evaluation.run_id
                items.append(item)
        return items, int(total or 0)
