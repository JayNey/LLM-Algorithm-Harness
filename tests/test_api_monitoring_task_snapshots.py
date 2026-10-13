"""Task monitoring reads real SQLite snapshots without queue side effects."""

import json
import re
from datetime import datetime
from unittest.mock import patch

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.dialects import postgresql

from api.db import make_engine, make_session_factory
from api.db.models import AsyncTask, Base, Evaluation
from api.monitoring.task_snapshots import _progress_field, read_task_snapshot


@pytest.fixture
def engine(tmp_path):
    value = make_engine(f"sqlite:///{tmp_path / 'snapshot.sqlite3'}")
    Base.metadata.create_all(value)
    try:
        yield value
    finally:
        value.dispose()


def add_evaluation(engine, task_id, status="pending", **changes):
    with make_session_factory(engine)() as session, session.begin():
        session.add(
            Evaluation(
                **{
                    "id": task_id,
                    "user_id": "owner-legacy",
                    "status": status,
                    "problem_count": 4,
                    "completed_count": 1,
                    "created_at": datetime(2026, 10, 13),
                    **changes,
                }
            )
        )


def add_async(engine, task_id, status="pending", **changes):
    with make_session_factory(engine)() as session, session.begin():
        session.add(
            AsyncTask(
                **{
                    "id": task_id,
                    "celery_task_id": "broker-id-" + task_id,
                    "user_id": "owner-queue",
                    "entity_id": "entity-" + task_id,
                    "task_type": "evaluation",
                    "status": status,
                    "progress": {"current": 2, "total": 6},
                    "created_at": datetime(2026, 10, 13),
                    **changes,
                }
            )
        )


def test_linked_evaluation_is_not_counted_as_legacy_task(engine):
    add_async(engine, "async-1", "running")
    add_evaluation(engine, "linked-1", "running", async_task_id="async-1")
    add_evaluation(engine, "legacy-1")

    legacy = read_task_snapshot(engine)
    queue = read_task_snapshot(engine, task_source="async_task")
    assert legacy["task_source"] == "legacy_evaluation"
    assert legacy["source"] == "persisted_business_evaluations"
    assert legacy["execution_backend"] == "in_process_simulator"
    assert legacy["production_queue_configured"] is False
    assert legacy["total"] == 1 and legacy["counts"] == {"pending": 1}
    assert legacy["items"] == [
        {
            "task_id": "legacy-1",
            "owner_id": "owner-legacy",
            "status": "pending",
            "completed": 1,
            "total": 4,
        }
    ]
    assert queue["task_source"] == "async_task"
    assert queue["source"] == "persisted_async_tasks"
    assert queue["execution_backend"] == "celery"
    assert queue["queue_infrastructure_available"] is True
    assert queue["real_evaluation_available"] is False
    assert queue["evaluation_worker_implementation"] == "mock"
    assert "production_queue_configured" not in queue
    assert queue["total"] == 1 and queue["counts"] == {"running": 1}
    assert queue["items"] == [
        {
            "task_id": "async-1",
            "owner_id": "owner-queue",
            "status": "running",
            "completed": 2,
            "total": 6,
            "task_type": "evaluation",
        }
    ]


@pytest.mark.parametrize("source", ["legacy_evaluation", "async_task"])
def test_counts_cover_matching_source_before_pagination(engine, source):
    add = add_evaluation if source == "legacy_evaluation" else add_async
    for task_id, state in (("a", "running"), ("b", "paused"), ("c", "running")):
        add(engine, task_id, state)
    page = read_task_snapshot(engine, limit=1, offset=1, task_source=source)
    assert page["status"] == "ok"
    assert page["total"] == 3 and page["counts"] == {"paused": 1, "running": 2}
    assert [item["task_id"] for item in page["items"]] == ["b"]
    filtered = read_task_snapshot(engine, "running", limit=1, offset=1, task_source=source)
    assert filtered["total"] == 2 and filtered["counts"] == {"running": 2}
    assert [item["task_id"] for item in filtered["items"]] == ["c"]
    beyond = read_task_snapshot(engine, offset=999, task_source=source)
    assert beyond["total"] == 3 and beyond["items"] == []


@pytest.mark.parametrize(
    "progress",
    [
        None,
        {},
        {"current": 1},
        {"current": 1, "total": None},
        {"current": True, "total": 2},
        {"current": 1, "total": False},
        {"current": 1.0, "total": 2},
        {"current": 1, "total": 2.5},
        {"current": "1", "total": 2},
        {"current": 1, "total": "2"},
        {"current": -1, "total": 2},
        {"current": 1, "total": -2},
        {"current": 3, "total": 2},
        {"current": 0, "total": 10**25},
        {"current": ["private-token"], "total": 2},
        {"current": {"private": "private-token"}, "total": 2},
        [1, 2, "private-token"],
        "private-token",
    ],
)
def test_invalid_json_progress_is_null_and_never_exposes_raw_values(engine, progress):
    add_async(engine, "task", progress=progress, error_message="error-private-token")
    snapshot = read_task_snapshot(engine, task_source="async_task")
    assert snapshot["status"] == "ok"
    assert snapshot["items"][0]["completed"] is None
    assert snapshot["items"][0]["total"] is None
    encoded = json.dumps(snapshot)
    for forbidden in ("private-token", "error_message", "celery_task_id", "broker-id"):
        assert forbidden not in encoded


@pytest.mark.parametrize("current,total", [(0, 0), (0, 3), (3, 3), (2**63 - 1, 2**63 - 1)])
def test_valid_json_progress_and_extra_secret_fields(engine, current, total):
    add_async(
        engine,
        "task",
        progress={
            "current": current,
            "total": total,
            "message": "message-private-token",
            "params": {"api_key": "params-private-token"},
            "huge": "private-token" * 100000,
        },
    )
    snapshot = read_task_snapshot(engine, task_source="async_task")
    assert snapshot["items"][0]["completed"] == current
    assert snapshot["items"][0]["total"] == total
    assert "private-token" not in json.dumps(snapshot)


@pytest.mark.parametrize("current,total", [(-1, 4), (5, 4), (1, -4), (1.5, 4)])
def test_invalid_legacy_progress_does_not_claim_completion(engine, current, total):
    add_evaluation(engine, "task", completed_count=current, problem_count=total)
    item = read_task_snapshot(engine)["items"][0]
    assert item["completed"] is None and item["total"] is None


def test_unknown_type_and_status_are_not_raw_strings(engine):
    add_async(engine, "task", "secret-status", task_type="secret-type")
    snapshot = read_task_snapshot(engine, task_source="async_task")
    assert snapshot["counts"] == {"other": 1}
    assert snapshot["items"][0]["status"] == "other"
    assert snapshot["items"][0]["task_type"] == "other"
    assert "secret-" not in json.dumps(snapshot)


@pytest.mark.parametrize("task_type", ["evaluation", "experiment", "benchmark", "import"])
def test_known_task_types_are_preserved(engine, task_type):
    add_async(engine, "task", task_type=task_type)
    assert (
        read_task_snapshot(engine, task_source="async_task")["items"][0]["task_type"] == task_type
    )


def test_source_queries_are_read_only_and_bound_to_actual_engine(engine, tmp_path):
    add_async(engine, "one")
    add_evaluation(engine, "legacy-one")
    other = make_engine(f"sqlite:///{tmp_path / 'other.sqlite3'}")
    Base.metadata.create_all(other)
    statements = []

    def observe(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        with patch("src.task_manager.TaskManager.get_task", side_effect=AssertionError("poll")):
            assert read_task_snapshot(engine)["total"] == 1
            assert read_task_snapshot(engine, task_source="async_task")["total"] == 1
            assert read_task_snapshot(other)["total"] == 0
            assert read_task_snapshot(other, task_source="async_task")["total"] == 0
    finally:
        event.remove(engine, "before_cursor_execute", observe)
        other.dispose()
    assert statements
    assert all(sql.lstrip().upper().startswith(("SELECT", "BEGIN")) for sql in statements)
    projected = [sql for sql in statements if "substr(" in sql]
    assert len(projected) == 1
    assert not re.search(r"(?:SELECT |,\s*)async_tasks\.progress(?:,|\s+AS|\s+FROM)", projected[0])
    assert "async_tasks.celery_task_id" not in projected[0]
    assert "async_tasks.error_message" not in projected[0]


def test_count_and_page_share_snapshot_during_concurrent_commit(engine):
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA journal_mode=WAL")
    add_async(engine, "a")
    add_async(engine, "b")
    inserted = False

    def insert_after_count(_conn, _cursor, statement, _params, _context, _many):
        nonlocal inserted
        if "GROUP BY" in statement and not inserted:
            inserted = True
            add_async(engine, "c")

    event.listen(engine, "after_cursor_execute", insert_after_count)
    try:
        snapshot = read_task_snapshot(engine, task_source="async_task")
    finally:
        event.remove(engine, "after_cursor_execute", insert_after_count)
    assert inserted
    assert snapshot["status"] == "ok" and snapshot["total"] == 2
    assert [item["task_id"] for item in snapshot["items"]] == ["a", "b"]
    with engine.connect() as connection:
        assert connection.scalar(select(func.count()).select_from(AsyncTask)) == 3


@pytest.mark.parametrize("source", ["legacy_evaluation", "async_task"])
def test_connection_failures_are_unknown_counts_and_hide_exception(engine, source):
    secret = "postgresql://user:private-token@example.org/private/path"
    with patch.object(engine, "connect", side_effect=RuntimeError(secret)):
        snapshot = read_task_snapshot(engine, task_source=source)
    assert snapshot["status"] == "unavailable"
    assert snapshot["items"] is None and snapshot["total"] is None and snapshot["counts"] is None
    assert secret not in json.dumps(snapshot)


def test_invalid_persisted_json_reports_unavailable_without_echoing_it(engine):
    add_async(engine, "task")
    with engine.begin() as connection:
        connection.execute(
            text("UPDATE async_tasks SET progress=:value"), {"value": "private-token"}
        )
    snapshot = read_task_snapshot(engine, task_source="async_task")
    assert snapshot["status"] == "unavailable"
    assert snapshot["items"] is None and snapshot["counts"] is None
    assert "private-token" not in json.dumps(snapshot)


@pytest.mark.parametrize(
    "arguments",
    [
        {"limit": 0},
        {"limit": 1001},
        {"limit": True},
        {"offset": -1},
        {"offset": 100001},
        {"offset": True},
        {"task_source": "private-source"},
        {"state": "private-status"},
    ],
)
def test_invalid_arguments_fail_before_connect(engine, arguments):
    with patch.object(engine, "connect", side_effect=AssertionError("connected")):
        with pytest.raises(ValueError):
            read_task_snapshot(engine, **arguments)


def test_postgresql_progress_projection_compiles_without_server():
    query = select(
        _progress_field("postgresql", "current").label("current"),
        _progress_field("postgresql", "total").label("total"),
    )
    sql = str(query.compile(dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}))
    assert "json_typeof" in sql and "->>" in sql
    assert "length(" in sql and "substr(" in sql
    assert "AS INTEGER" not in sql  # Malformed JSON numbers must not fail a DB integer cast.
    assert "'current'" in sql and "'total'" in sql
    assert "async_tasks.progress," not in sql
