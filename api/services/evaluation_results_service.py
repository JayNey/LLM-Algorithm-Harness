"""Owner-scoped queries over stored evaluation results.

Routes stay thin. This service resolves a run for its owner, aggregates every
unit in that run, and applies the list filters.
"""

from __future__ import annotations

import csv
import io
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, String, and_, bindparam, exists, func, inspect, or_, select
from sqlalchemy.engine import Engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.sql.visitors import InternalTraversal

from api.db import (
    BenchmarkRun,
    Evaluation,
    EvaluationResult,
    Problem,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.engine import business_database_url
from api.db.migrate import SCRIPT_LOCATION
from src.error_analysis import normalize_message
from src.models import ExecutionResult, IterationResult
from src.reporting.capability_profiler import (
    calculate_dimension_scores,
    format_dimension_scores_for_radar,
    get_dimension_problem_counts,
)
from src.reporting.html_generator import HTMLGenerator
from src.reporting.markdown_generator import MarkdownGenerator

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


def _by_difficulty(
    items: list[tuple[EvaluationResult, Problem | None]],
) -> dict[str, dict[str, float | int]]:
    """Group one strategy with the same difficulty rule as analytics."""
    grouped: dict[str, list[EvaluationResult]] = {}
    for row, problem in items:
        difficulty = _effective_difficulty(row.metrics, problem)
        if not difficulty:
            continue
        grouped.setdefault(difficulty, []).append(row)
    summary: dict[str, dict[str, float | int]] = {}
    for name, rows in grouped.items():
        solved = sum(1 for row in rows if row.status == "success")
        summary[name] = {
            "success_rate": solved / len(rows),
            "solved": solved,
            "total": len(rows),
        }
    return summary


def aggregate(pairs: list[tuple[EvaluationResult, Problem | None]]) -> list[dict]:
    """Summarize every unit of a run, grouped by strategy.

    Difficulty comes from metrics when that value is present and not null,
    otherwise from the joined problem. Later analytics and comparison reuse
    this so a detail page and a chart cannot drift apart. Cost skips units
    flagged cost_unknown.
    """
    grouped: dict[str, list[tuple[EvaluationResult, Problem | None]]] = {}
    for pair in pairs:
        grouped.setdefault(pair[0].strategy_name, []).append(pair)
    strategies = []
    for name, items in grouped.items():
        rows = [row for row, _problem in items]
        solved = sum(1 for row in rows if row.status == "success")
        estimated_cost, unknown_cost = _known_cost(rows)
        times = [
            value
            for row in rows
            if (value := _num(row.metrics, "execution_time_seconds")) is not None
        ]
        tokens = [value for row in rows if (value := _num(row.metrics, "total_tokens")) is not None]
        strategies.append(
            {
                "name": name,
                "success_rate": solved / len(rows) if rows else 0.0,
                "total_problems": len(rows),
                "solved_problems": solved,
                "avg_tokens": (sum(tokens) / len(tokens)) if tokens else 0.0,
                "estimated_cost_usd": estimated_cost,
                "unknown_cost_count": unknown_cost,
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


class _JsonArrayContains(ColumnElement[bool]):
    """Case-sensitive membership of one decoded JSON array element.

    The tag stays a bound parameter. SQLite reads json_each. PostgreSQL uses
    jsonb containment so a null or non-array value does not abort the query.
    Neither compares a LIKE pattern against JSON text.
    """

    inherit_cache = True
    type = Boolean()
    _traverse_internals = [
        ("column", InternalTraversal.dp_clauseelement),
        ("value", InternalTraversal.dp_string),
    ]

    def __init__(self, column, value: str):
        self.column = column
        self.value = value


def _tag_bind(element: _JsonArrayContains, compiler, **kw) -> str:
    return compiler.process(bindparam(None, element.value, type_=String()), **kw)


@compiles(_JsonArrayContains)
def _compile_json_array_contains_sqlite(element, compiler, **kw) -> str:
    column = compiler.process(element.column, **kw)
    return (
        f"EXISTS (SELECT 1 FROM json_each({column}) AS tag_element "
        f"WHERE tag_element.value = {_tag_bind(element, compiler, **kw)} "
        f"AND tag_element.type = 'text')"
    )


@compiles(_JsonArrayContains, "postgresql")
def _compile_json_array_contains_postgresql(element, compiler, **kw) -> str:
    column = compiler.process(element.column, **kw)
    # CAST(NULL AS jsonb) is null. null @> array is unknown and drops the row.
    return f"(CAST({column} AS jsonb) @> jsonb_build_array({_tag_bind(element, compiler, **kw)}))"


def _json_array_contains(column, value: str):
    """Match one decoded JSON string. The tag is bound, not interpolated."""
    return _JsonArrayContains(column, value)


def _effective_difficulty(metrics: dict | None, problem: Problem | None) -> str | None:
    """Prefer the difficulty saved on the unit, then the problem record."""
    if metrics is not None and "difficulty" in metrics and metrics["difficulty"] is not None:
        return str(metrics["difficulty"])
    if problem is not None and problem.difficulty:
        return str(problem.difficulty)
    return None


def _rate_bucket(rows: list[EvaluationResult]) -> dict[str, float | int]:
    solved = sum(1 for row in rows if row.status == "success")
    total = len(rows)
    return {
        "success_rate": (solved / total) if total else 0.0,
        "solved": solved,
        "total": total,
    }


def _group_rates(pairs: list[tuple[EvaluationResult, Problem | None]], labeler) -> dict:
    """Count each unit once per label. Overall totals stay on the ungrouped rows."""
    grouped: dict[str, list[EvaluationResult]] = {}
    for row, problem in pairs:
        seen: set[str] = set()
        for label in labeler(row, problem):
            if not label or label in seen:
                continue
            seen.add(label)
            grouped.setdefault(label, []).append(row)
    return {name: _rate_bucket(items) for name, items in grouped.items()}


def _difficulty_labels(row: EvaluationResult, problem: Problem | None) -> list[str]:
    difficulty = _effective_difficulty(row.metrics, problem)
    return [difficulty] if difficulty else []


def _tag_labels(_row: EvaluationResult, problem: Problem | None) -> list[str]:
    if problem is None or not problem.tags:
        return []
    return [str(tag) for tag in problem.tags]


def _known_cost(rows: list[EvaluationResult]) -> tuple[float, int]:
    """Sum cost_usd, skipping units flagged cost_unknown. Same rule as aggregate()."""
    known = [
        float((row.metrics or {}).get("cost_usd") or 0)
        for row in rows
        if not (row.metrics or {}).get("cost_unknown")
    ]
    unknown = sum(1 for row in rows if (row.metrics or {}).get("cost_unknown"))
    return sum(known), unknown


def _success_payload(pairs: list[tuple[EvaluationResult, Problem | None]]) -> dict:
    rows = [row for row, _problem in pairs]
    times = [
        value for row in rows if (value := _num(row.metrics, "execution_time_seconds")) is not None
    ]
    payload = _rate_bucket(rows)
    payload["avg_execution_time"] = (sum(times) / len(times)) if times else 0.0
    payload["by_difficulty"] = _group_rates(pairs, _difficulty_labels)
    payload["by_tag"] = _group_rates(pairs, _tag_labels)
    return payload


def _tokens_payload(pairs: list[tuple[EvaluationResult, Problem | None]]) -> dict:
    rows = [row for row, _problem in pairs]
    tokens = [value for row in rows if (value := _num(row.metrics, "total_tokens")) is not None]
    estimated, unknown = _known_cost(rows)
    return {
        "total_tokens": sum(tokens),
        "avg_tokens": (sum(tokens) / len(tokens)) if tokens else 0.0,
        "estimated_cost_usd": estimated,
        "unknown_cost_count": unknown,
    }


def _iterations_payload(pairs: list[tuple[EvaluationResult, Problem | None]]) -> dict:
    """Aggregate metrics.iterations. A missing key is unknown, not zero."""
    known: list = []
    unknown = 0
    for row, _problem in pairs:
        metrics = row.metrics
        if metrics is None or "iterations" not in metrics or metrics["iterations"] is None:
            unknown += 1
            continue
        known.append(metrics["iterations"])
    return {
        "known_count": len(known),
        "unknown_count": unknown,
        "average": (sum(known) / len(known)) if known else None,
        "distribution": [
            {"iterations": value, "count": count} for value, count in sorted(Counter(known).items())
        ],
    }


def _failure_modes_payload(pairs: list[tuple[EvaluationResult, Problem | None]]) -> dict:
    """Count saved failure_mode on non-success rows. A missing mode is unknown."""
    counts: Counter[str] = Counter()
    for row, _problem in pairs:
        if row.status == "success":
            continue
        counts[(row.metrics or {}).get("failure_mode") or "unknown"] += 1
    return dict(counts)


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


# Copied from CSVExporter.export. This service writes the rows itself.
_CSV_FIELDNAMES = [
    "problem_id",
    "strategy",
    "status",
    "failure_category",
    "passed",
    "tokens",
    "time",
    "iterations",
    "error_message",
    "total_tests",
    "passed_tests",
    "failed_tests",
    "formal_evaluable",
    "formal_passed",
    "sample_only",
    "hidden_total_tests",
    "hidden_passed_tests",
    "hidden_failed_tests",
]
_FAILURE_CATEGORIES = frozenset(
    {
        "wrong_answer",
        "code_extraction_failed",
        "model_error",
        "system_error",
        "unsupported",
        "budget_exhausted",
    }
)
_FAILURE_MODES = frozenset(
    {
        "syntax_error",
        "logic_error",
        "timeout",
        "boundary_condition",
        "understanding_error",
        "runtime_error",
        "infrastructure_error",
        "unknown",
    }
)
_DIFFICULTIES = frozenset({"easy", "medium", "hard"})


def _stored_iterations(metrics: dict | None) -> int | None:
    """Return a saved iteration count. A missing key stays unknown."""
    if metrics is None or "iterations" not in metrics or metrics["iterations"] is None:
        return None
    value = metrics["iterations"]
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value)


def _allowed(metrics: dict, key: str, choices: frozenset[str]) -> str | None:
    value = metrics.get(key)
    if isinstance(value, str) and value in choices:
        return value
    return None


def _execution_result(row: EvaluationResult) -> ExecutionResult:
    """In-memory result for the report generators. Nothing here is persisted."""
    metrics = row.metrics or {}
    count = _stored_iterations(row.metrics)
    iterations = (
        [IterationResult(iteration=index) for index in range(1, count + 1)]
        if count is not None and count > 0
        else []
    )
    return ExecutionResult(
        problem_id=row.problem_id,
        strategy=row.strategy_name,
        generated_code="",
        status=row.status,
        failure_category=_allowed(metrics, "failure_category", _FAILURE_CATEGORIES),  # type: ignore[arg-type]
        failure_mode=_allowed(metrics, "failure_mode", _FAILURE_MODES),  # type: ignore[arg-type]
        difficulty=_allowed(metrics, "difficulty", _DIFFICULTIES),  # type: ignore[arg-type]
        iterations=iterations,
        error_message=row.error_message,
        total_tokens=int(metrics.get("total_tokens") or 0),
        execution_time_seconds=float(metrics.get("execution_time_seconds") or 0.0),
    )


def _generator_metrics(
    pairs: list[tuple[EvaluationResult, Problem | None]],
) -> dict[str, dict]:
    """Strategy summaries in the shape MarkdownGenerator and HTMLGenerator read."""
    metrics: dict[str, dict] = {}
    for item in aggregate(pairs):
        payload = {
            "success_rate": item["success_rate"],
            "solved_problems": item["solved_problems"],
            "total_problems": item["total_problems"],
            "avg_tokens_per_problem": item["avg_tokens"],
            "avg_time_per_problem": item["avg_execution_time"],
            "estimated_cost_usd": item["estimated_cost_usd"],
            "by_difficulty": item["by_difficulty"],
        }
        if item["unknown_cost_count"] and item["estimated_cost_usd"] == 0:
            payload["pricing_metadata"] = {"unknown_usage": True}
        metrics[str(item["name"])] = payload
    return metrics


def _execution_results(rows: list[EvaluationResult]) -> dict[str, list[ExecutionResult]]:
    grouped: dict[str, list[ExecutionResult]] = {}
    for row in rows:
        grouped.setdefault(row.strategy_name, []).append(_execution_result(row))
    return grouped


def _csv_text(rows: list[EvaluationResult]) -> str:
    """UTF-8 BOM CSV. Unstored test counts and a missing iterations key stay blank."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=_CSV_FIELDNAMES)
    writer.writeheader()
    for row in rows:
        metrics = row.metrics or {}
        count = _stored_iterations(row.metrics)
        tokens = metrics.get("total_tokens")
        elapsed = metrics.get("execution_time_seconds")
        record = {name: "" for name in _CSV_FIELDNAMES}
        record.update(
            {
                "problem_id": row.problem_id,
                "strategy": row.strategy_name,
                "status": row.status,
                "failure_category": metrics.get("failure_category") or "",
                "passed": row.status == "success",
                "tokens": "" if tokens is None else tokens,
                "time": "" if elapsed is None else round(float(elapsed), 3),
                "iterations": "" if count is None else count,
                "error_message": row.error_message or "",
            }
        )
        writer.writerow(record)
    return "\ufeff" + buffer.getvalue()


def _generated_text(write) -> str:
    with tempfile.TemporaryDirectory() as directory:
        return write(str(Path(directory) / "report"))


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
            pairs = self._unit_pairs(session, evaluation.id)
            rows = [row for row, _problem in pairs]
            total = len(rows)
            page = rows[offset : offset + limit]
            return {
                "run_id": evaluation.run_id,
                "status": evaluation.status,
                "created_at": _iso(evaluation.created_at),
                "completed_at": _iso(evaluation.completed_at),
                "strategies": aggregate(pairs),
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
        primary = column.desc().nulls_last() if descending else column.asc().nulls_first()
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

    def _analytics_pairs(
        self,
        session: Session,
        owner_id: str,
        *,
        run_id: str | None,
        strategy: str | None,
        difficulty: str | None,
        tag: str | None,
    ) -> list[tuple[EvaluationResult, Problem | None]]:
        """Units in scope. No run_id means this user's completed evaluations only."""
        if run_id is not None:
            evaluation_ids = [self._resolve(session, owner_id, run_id).id]
        else:
            evaluation_ids = list(
                session.scalars(
                    select(Evaluation.id).where(
                        Evaluation.user_id == owner_id,
                        Evaluation.status == "completed",
                    )
                ).all()
            )
        if not evaluation_ids:
            return []
        stmt = (
            select(EvaluationResult, Problem)
            .outerjoin(Problem, Problem.problem_id == EvaluationResult.problem_id)
            .where(EvaluationResult.evaluation_id.in_(evaluation_ids))
        )
        if strategy is not None:
            stmt = stmt.where(EvaluationResult.strategy_name == strategy)
        selected: list[tuple[EvaluationResult, Problem | None]] = []
        for row, problem in session.execute(stmt).all():
            if difficulty is not None and _effective_difficulty(row.metrics, problem) != difficulty:
                continue
            if tag is not None:
                tags = list(problem.tags or []) if problem is not None else []
                if tag not in tags:
                    continue
            selected.append((row, problem))
        return selected

    def _analytics(self, owner_id: str, builder, **filters) -> dict:
        with self._session() as session:
            pairs = self._analytics_pairs(session, owner_id, **filters)
            return builder(pairs)

    def success_rate(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Overall, per-difficulty, and per-tag success over the scoped units."""
        return self._analytics(
            owner_id,
            _success_payload,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )

    def tokens(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Token totals and cost. cost_unknown units stay out of the USD sum."""
        return self._analytics(
            owner_id,
            _tokens_payload,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )

    def iterations(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Known iteration counts, the unknown count, and the distribution."""
        return self._analytics(
            owner_id,
            _iterations_payload,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )

    def failure_modes(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Saved failure_mode counts for units that did not succeed."""
        return self._analytics(
            owner_id,
            _failure_modes_payload,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )

    def _units(self, session: Session, evaluation_id: str) -> list[EvaluationResult]:
        return list(
            session.scalars(
                select(EvaluationResult)
                .where(EvaluationResult.evaluation_id == evaluation_id)
                .order_by(EvaluationResult.created_at, EvaluationResult.id)
            ).all()
        )

    def _unit_pairs(
        self, session: Session, evaluation_id: str
    ) -> list[tuple[EvaluationResult, Problem | None]]:
        """Units for one evaluation, with the problem used for difficulty and tags."""
        return list(
            session.execute(
                select(EvaluationResult, Problem)
                .outerjoin(Problem, Problem.problem_id == EvaluationResult.problem_id)
                .where(EvaluationResult.evaluation_id == evaluation_id)
                .order_by(EvaluationResult.created_at, EvaluationResult.id)
            ).all()
        )

    def compare_strategies(self, owner_id: str, run_id: str) -> dict:
        """Strategy totals for one run. Same aggregate as the result detail."""
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            return {"strategies": aggregate(self._unit_pairs(session, evaluation.id))}

    def compare_models(self, owner_id: str) -> dict:
        """Group this user's completed runs by model, then aggregate each group."""
        with self._session() as session:
            evaluations = session.scalars(
                select(Evaluation)
                .where(Evaluation.user_id == owner_id, Evaluation.status == "completed")
                .order_by(Evaluation.model, Evaluation.id)
            ).all()
            grouped: dict[str | None, list[tuple[EvaluationResult, Problem | None]]] = {}
            for evaluation in evaluations:
                grouped.setdefault(evaluation.model, []).extend(
                    self._unit_pairs(session, evaluation.id)
                )
            return {
                "models": [
                    {"model": model, "strategies": aggregate(pairs)}
                    for model, pairs in grouped.items()
                ]
            }

    def compare_history(self, owner_id: str, run_id: str) -> dict:
        """Other completed runs with the same model and strategy set.

        The current run is excluded. Points follow completion time, then id.
        """
        with self._session() as session:
            current = self._resolve(session, owner_id, run_id)
            wanted = set(current.strategy_names or [])
            candidates = session.scalars(
                select(Evaluation)
                .where(
                    Evaluation.user_id == owner_id,
                    Evaluation.status == "completed",
                    Evaluation.id != current.id,
                    Evaluation.model == current.model,
                )
                .order_by(Evaluation.completed_at, Evaluation.id)
            ).all()
            series = []
            for evaluation in candidates:
                if set(evaluation.strategy_names or []) != wanted:
                    continue
                series.append(
                    {
                        "run_id": evaluation.run_id,
                        "completed_at": _iso(evaluation.completed_at),
                        "strategies": aggregate(self._unit_pairs(session, evaluation.id)),
                    }
                )
            return {"series": series}

    def _sorted_pairs(
        self,
        session: Session,
        owner_id: str,
        *,
        run_id: str | None,
        strategy: str | None,
        difficulty: str | None,
        tag: str | None,
    ) -> list[tuple[EvaluationResult, Problem | None]]:
        """Filtered units in the same order as a result detail."""
        pairs = self._analytics_pairs(
            session,
            owner_id,
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )
        pairs.sort(key=lambda pair: (pair[0].created_at, pair[0].id))
        return pairs

    def _strategy_summaries(
        self,
        owner_id: str,
        *,
        run_id: str | None,
        strategy: str | None,
        difficulty: str | None,
        tag: str | None,
    ) -> list[dict]:
        """Per-strategy aggregate shared with result detail."""
        with self._session() as session:
            pairs = self._sorted_pairs(
                session,
                owner_id,
                run_id=run_id,
                strategy=strategy,
                difficulty=difficulty,
                tag=tag,
            )
            return aggregate(pairs)

    def success_rate_chart(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """One success-rate point per strategy, using the detail aggregate."""
        summaries = self._strategy_summaries(
            owner_id, run_id=run_id, strategy=strategy, difficulty=difficulty, tag=tag
        )
        return {
            "points": [
                {"name": item["name"], "success_rate": item["success_rate"]} for item in summaries
            ]
        }

    def token_chart(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """One line per strategy. Each point is one problem's stored tokens."""
        with self._session() as session:
            pairs = self._sorted_pairs(
                session,
                owner_id,
                run_id=run_id,
                strategy=strategy,
                difficulty=difficulty,
                tag=tag,
            )
            grouped: dict[str, list[dict]] = {}
            for row, _problem in pairs:
                grouped.setdefault(row.strategy_name, []).append(
                    {
                        "problem_id": row.problem_id,
                        "tokens": (row.metrics or {}).get("total_tokens"),
                    }
                )
        return {"series": [{"name": name, "points": points} for name, points in grouped.items()]}

    def cost_accuracy(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """One point per strategy: success rate and known estimated cost."""
        summaries = self._strategy_summaries(
            owner_id, run_id=run_id, strategy=strategy, difficulty=difficulty, tag=tag
        )
        return {
            "points": [
                {
                    "name": item["name"],
                    "success_rate": item["success_rate"],
                    "estimated_cost_usd": item["estimated_cost_usd"],
                }
                for item in summaries
            ]
        }

    def capability_radar(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Radar series named by evaluations.model. Missing dimensions score 0."""
        with self._session() as session:
            pairs = self._sorted_pairs(
                session,
                owner_id,
                run_id=run_id,
                strategy=strategy,
                difficulty=difficulty,
                tag=tag,
            )
            evaluation_ids = {row.evaluation_id for row, _problem in pairs}
            model_by_id: dict[str, str | None] = {}
            if evaluation_ids:
                evaluations = session.scalars(
                    select(Evaluation).where(Evaluation.id.in_(evaluation_ids))
                ).all()
                model_by_id = {item.id: item.model for item in evaluations}
            result_dicts = [
                {
                    "problem_id": row.problem_id,
                    "model": model_by_id.get(row.evaluation_id),
                    "status": row.status,
                }
                for row, _problem in pairs
            ]
            problem_dicts: list[dict] = []
            seen: set[str] = set()
            for row, problem in pairs:
                if row.problem_id in seen:
                    continue
                seen.add(row.problem_id)
                tags = list(problem.tags or []) if problem is not None else []
                problem_dicts.append({"problem_id": row.problem_id, "tags": tags})
        scores = calculate_dimension_scores(result_dicts, problem_dicts)
        formatted = format_dimension_scores_for_radar(scores)
        return {
            "dimensions": formatted["dimension_names"],
            "series": [
                {"name": name, "data": values} for name, values in formatted["model_scores"].items()
            ],
            "problem_counts": get_dimension_problem_counts(problem_dicts),
        }

    def failure_summary(self, owner_id: str, run_id: str) -> dict:
        """Count stored modes and categories. Cluster saved messages only."""
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            rows = self._units(session, evaluation.id)
        modes: Counter[str] = Counter()
        categories: Counter[str] = Counter()
        clusters: Counter[str] = Counter()
        for row in rows:
            if row.status == "success":
                continue
            metrics = row.metrics or {}
            modes[metrics.get("failure_mode") or "unknown"] += 1
            categories[metrics.get("failure_category") or "unknown"] += 1
            if row.error_message:
                clusters[normalize_message(row.error_message)] += 1
        return {
            "modes": dict(modes),
            "categories": dict(categories),
            "clusters": [
                {"pattern": pattern, "count": count}
                for pattern, count in clusters.most_common()
                if pattern
            ],
        }

    def failures_by_tag(
        self,
        owner_id: str,
        *,
        run_id: str | None = None,
        strategy: str | None = None,
        difficulty: str | None = None,
        tag: str | None = None,
    ) -> dict:
        """Success rate, solved, and total for each problem tag in scope."""
        return self._analytics(
            owner_id,
            lambda pairs: {"tags": _group_rates(pairs, _tag_labels)},
            run_id=run_id,
            strategy=strategy,
            difficulty=difficulty,
            tag=tag,
        )

    def failure_cases(self, owner_id: str, run_id: str) -> dict:
        """Non-success units for one run, with the stored error message."""
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            rows = self._units(session, evaluation.id)
        return {
            "items": [
                {
                    "problem_id": row.problem_id,
                    "strategy": row.strategy_name,
                    "status": row.status,
                    "error_message": row.error_message,
                }
                for row in rows
                if row.status != "success"
            ]
        }

    def learning_curve(self, owner_id: str, suite_id: str | None = None) -> dict:
        """Completed benchmark runs for this user, oldest completion first."""
        with self._session() as session:
            stmt = select(BenchmarkRun).where(
                BenchmarkRun.user_id == owner_id,
                BenchmarkRun.status == "completed",
            )
            if suite_id is not None:
                stmt = stmt.where(BenchmarkRun.suite_id == suite_id)
            rows = session.scalars(stmt.order_by(BenchmarkRun.completed_at, BenchmarkRun.id)).all()
            return {
                "series": [
                    {
                        "suite_id": row.suite_id,
                        "timestamp": _iso(row.completed_at),
                        "model": row.model,
                        "accuracy": row.accuracy,
                        "cost_usd": row.cost_usd,
                    }
                    for row in rows
                ]
            }

    def _report_inputs(
        self, owner_id: str, run_id: str
    ) -> tuple[dict[str, dict], dict[str, list[ExecutionResult]], dict | None]:
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            pairs = self._unit_pairs(session, evaluation.id)
            rows = [row for row, _problem in pairs]
            config = {"model": evaluation.model} if evaluation.model else None
            return _generator_metrics(pairs), _execution_results(rows), config

    def report_markdown(self, owner_id: str, run_id: str) -> str:
        """Markdown body from MarkdownGenerator. The temporary file is deleted."""
        metrics, results, config = self._report_inputs(owner_id, run_id)
        return _generated_text(
            lambda path: MarkdownGenerator.generate(metrics, results, path, config=config)
        )

    def report_html(self, owner_id: str, run_id: str) -> str:
        """HTML body from HTMLGenerator, including its existing charts."""
        metrics, results, config = self._report_inputs(owner_id, run_id)
        return _generated_text(
            lambda path: HTMLGenerator.generate(
                metrics, results, path, include_charts=True, config=config
            )
        )

    def report_csv(self, owner_id: str, run_id: str) -> str:
        """CSV text for one owned run. Does not call CSVExporter.export."""
        with self._session() as session:
            evaluation = self._resolve(session, owner_id, run_id)
            return _csv_text(self._units(session, evaluation.id))
