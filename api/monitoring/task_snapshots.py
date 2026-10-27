"""Read bounded task snapshots without polling Celery or changing task state."""

from typing import Any

from sqlalchemy import Engine, String, and_, case, cast, func, select
from sqlalchemy.sql.elements import ColumnElement

from api.db.models import AsyncTask, Evaluation
from api.monitoring.capabilities import evaluation_capability

_STATUSES = ("pending", "running", "paused", "completed", "failed", "cancelled")
_TASK_TYPES = ("evaluation", "experiment", "benchmark", "import", "ab_test")
_MAX_PROGRESS = 2**63 - 1
_PROGRESS_TEXT_LIMIT = 20


def _progress_field(backend: str, key: str) -> ColumnElement[Any]:
    """Project only a bounded JSON number, never the whole progress object.

    SQLite distinguishes JSON integers from booleans. PostgreSQL's JSON
    number type includes fractions, which the Python integer check rejects.
    Check text length before the projection so truncation cannot turn a huge
    number or a secret-bearing string into an apparently valid count.
    """
    value = cast(AsyncTask.progress[key].as_string(), String())
    if backend == "sqlite":
        numeric = func.json_type(AsyncTask.progress, "$." + key) == "integer"
    elif backend == "postgresql":
        numeric = func.json_typeof(AsyncTask.progress[key]) == "number"
    else:
        raise ValueError("Unsupported task snapshot database")
    return case(
        (
            and_(numeric, func.length(value) <= _PROGRESS_TEXT_LIMIT),
            func.substr(value, 1, _PROGRESS_TEXT_LIMIT),
        ),
        else_=None,
    )


def _progress(current: Any, total: Any) -> tuple[int | None, int | None]:
    def integer(value: Any) -> int | None:
        if isinstance(value, str):
            if not 1 <= len(value) <= _PROGRESS_TEXT_LIMIT or not value.isascii():
                return None
            if not value.isdecimal():
                return None
            value = int(value)
        if type(value) is not int or not 0 <= value <= _MAX_PROGRESS:
            return None
        return value

    current, total = integer(current), integer(total)
    if current is None or total is None or current > total:
        return None, None
    return current, total


def read_task_snapshot(
    engine: Engine,
    state: str | None = None,
    limit: int = 100,
    offset: int = 0,
    task_source: str = "legacy_evaluation",
) -> dict[str, Any]:
    """Count and page one persisted source within a single read snapshot.

    Linked evaluations are excluded from the legacy source; AsyncTask rows
    describe queue lifecycle. Neither source proves provider or sandbox
    readiness, nor does it measure real LLM evaluation performance.
    """
    if (
        type(limit) is not int
        or type(offset) is not int
        or not 1 <= limit <= 1000
        or not 0 <= offset <= 100000
    ):
        raise ValueError("Invalid task pagination")
    if state is not None and state not in _STATUSES:
        raise ValueError("Invalid task state")
    if task_source not in {"legacy_evaluation", "async_task"}:
        raise ValueError("Invalid task source")

    metadata: dict[str, Any] = {
        "limit": limit,
        "offset": offset,
        "task_source": task_source,
    }
    model: type[Evaluation] | type[AsyncTask]
    condition: list[ColumnElement[bool]]
    if task_source == "legacy_evaluation":
        model = Evaluation
        condition = [Evaluation.async_task_id.is_(None)]
        metadata.update(
            source="persisted_business_evaluations",
            execution_backend="unassigned_or_legacy",
            production_queue_configured=False,
        )
    else:
        model = AsyncTask
        condition = []
        metadata.update(
            source="persisted_async_tasks",
            execution_backend="celery",
            queue_infrastructure_available=True,
            **evaluation_capability(),
        )
    if state is not None:
        condition.append(model.status == state)
    status = case((model.status.in_(_STATUSES), model.status), else_="other")

    try:
        backend = engine.dialect.name
        if task_source == "legacy_evaluation":
            progress_columns = [
                Evaluation.completed_count.label("current"),
                Evaluation.problem_count.label("total"),
            ]
        else:
            progress_columns = [
                _progress_field(backend, "current").label("current"),
                _progress_field(backend, "total").label("total"),
            ]
        columns = [
            model.id.label("task_id"),
            model.user_id.label("owner_id"),
            status.label("status"),
            *progress_columns,
        ]
        if task_source == "async_task":
            columns.append(
                case(
                    (AsyncTask.task_type.in_(_TASK_TYPES), AsyncTask.task_type), else_="other"
                ).label("task_type")
            )
        count_query = (
            select(status.label("status"), func.count()).where(*condition).group_by(status)
        )
        page_query = (
            select(*columns)
            .where(*condition)
            .order_by(model.created_at, model.id)
            .limit(limit)
            .offset(offset)
        )
        with engine.connect() as connection:
            if backend == "postgresql":
                connection = connection.execution_options(isolation_level="REPEATABLE READ")
            with connection.begin():
                # The sqlite3 legacy transaction mode does not begin a read
                # transaction for SELECT, so explicitly pin both queries.
                if backend == "sqlite":
                    connection.exec_driver_sql("BEGIN")
                counts: dict[str, int] = dict(connection.execute(count_query).tuples().all())
                rows = connection.execute(page_query).mappings().all()
                items = []
                for row in rows:
                    current, total = _progress(row["current"], row["total"])
                    item = {
                        "task_id": row["task_id"],
                        "owner_id": row["owner_id"],
                        "status": row["status"],
                        "completed": current,
                        "total": total,
                    }
                    if task_source == "async_task":
                        item["task_type"] = row["task_type"]
                    items.append(item)
        return {
            **metadata,
            "status": "ok",
            "items": items,
            "total": sum(counts.values()),
            "counts": counts,
        }
    except Exception:
        return {
            **metadata,
            "status": "unavailable",
            "items": None,
            "total": None,
            "counts": None,
            "detail": "Business task snapshot could not be collected",
        }
