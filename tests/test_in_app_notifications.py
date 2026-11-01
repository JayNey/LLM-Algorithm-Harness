"""In-app notification storage, delivery and API (issue #328)."""

from datetime import datetime

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from api.db import (
    Evaluation,
    InAppNotification,
    downgrade,
    make_engine,
    make_session_factory,
    offline_upgrade_sql,
    run_migrations,
)
from api.services.in_app_notification_service import NotificationNotFound, NotificationService


def _row(
    note_id: str, user_id: str, event_key: str = "task-completed/evaluation/ev-1"
) -> InAppNotification:
    return InAppNotification(
        id=note_id,
        user_id=user_id,
        kind="task_completed",
        event_key=event_key,
        title_key="通知.任务完成.标题",
        body_key="通知.任务完成.正文",
        params={"entity_id": "ev-1"},
        created_at=datetime(2026, 11, 1, 8, 0, 0),
        resource_kind="evaluation",
        resource_id="ev-1",
        href="/evaluations/ev-1",
    )


def test_notification_migration_roundtrips_and_rejects_duplicate_events(tmp_path):
    url = f"sqlite:///{tmp_path}/notifications.sqlite3"
    run_migrations(url)
    engine = make_engine(url)
    assert "in_app_notifications" in inspect(engine).get_table_names()
    constraints = inspect(engine).get_unique_constraints("in_app_notifications")
    assert any({"user_id", "event_key"} <= set(item["column_names"]) for item in constraints)

    downgrade(url, "base")
    assert "in_app_notifications" not in inspect(make_engine(url)).get_table_names()
    assert "spend_records" not in inspect(make_engine(url)).get_table_names()

    run_migrations(url)
    engine = make_engine(url)
    factory = make_session_factory(engine)
    with factory() as db, db.begin():
        db.add(_row("note-1", "alice"))
        db.add(_row("note-2", "bob"))
    with pytest.raises(IntegrityError):
        with factory() as db, db.begin():
            db.add(_row("note-3", "alice"))
    with factory() as db:
        assert db.get(InAppNotification, "note-1") is not None
        assert db.get(InAppNotification, "note-3") is None
    engine.dispose()

    sql = offline_upgrade_sql("postgresql://user:pass@localhost:5432/business")
    assert "in_app_notifications" in sql
    assert "uq_in_app_notifications_user_event" in sql
    assert "sqlite" not in sql.lower()


def _stage(service: NotificationService, db, **overrides):
    payload = {
        "user_id": "alice",
        "kind": "task_completed",
        "event_key": "task-completed/evaluation/ev-1",
        "title_key": "任务已完成",
        "body_key": "已完成 {{completed_count}} / {{total_count}}",
        "params": {"entity_id": "ev-1", "completed_count": 1, "total_count": 1},
        "resource_kind": "evaluation",
        "resource_id": "ev-1",
        "href": "/evaluations/ev-1",
        "created_at": datetime(2026, 11, 1, 11, 0, 0),
    }
    payload.update(overrides)
    return service.stage(db, **payload)


def test_queries_page_unread_isolation_retention_and_redaction(tmp_path):
    now = datetime(2026, 11, 1, 12, 0, 0)
    service = NotificationService(f"sqlite:///{tmp_path}/query.sqlite3")
    with service._sessions() as db, db.begin():
        db.add(Evaluation(id="ev-1", user_id="alice"))
        newest = _stage(
            service,
            db,
            params={
                "entity_id": "ev-1",
                "completed_count": 2,
                "total_count": 3,
                "api_key": "sk-secret",
                "error_message": "provider exploded",
                "webhook": "https://hooks.example/secret",
            },
        )
        missing = _stage(
            service,
            db,
            event_key="task-completed/evaluation/missing",
            resource_id="missing",
            href="/evaluations/missing",
            created_at=datetime(2026, 11, 1, 10, 0, 0),
        )
        budget = _stage(
            service,
            db,
            kind="budget_alert",
            event_key="budget-alert/rule/80/10",
            title_key="预算达到阈值",
            body_key="已知费用达到预算的 {{threshold_pct}}%",
            params={"threshold_pct": 80, "used_usd": 8, "cap_usd": 10},
            resource_kind="budget",
            resource_id=None,
            href="/settings/budgets",
            created_at=datetime(2026, 11, 1, 9, 0, 0),
        )
        _stage(
            service,
            db,
            event_key="task-completed/evaluation/old",
            resource_id="old",
            created_at=datetime(2026, 7, 1, 0, 0, 0),
        )
        bob = _stage(
            service,
            db,
            user_id="bob",
            event_key="task-completed/evaluation/bob",
            resource_id="bob-ev",
            created_at=datetime(2026, 11, 1, 11, 30, 0),
        )
        newest_id, missing_id, budget_id, bob_id = newest.id, missing.id, budget.id, bob.id

    page = service.list_notifications("alice", limit=2, now=now)
    assert page["unread_count"] == 3
    assert [item["id"] for item in page["items"]] == [newest_id, missing_id]
    assert page["items"][0]["params"] == {
        "entity_id": "ev-1",
        "completed_count": 2,
        "total_count": 3,
    }
    assert page["items"][0]["href"] == "/evaluations/ev-1"
    assert page["items"][1]["resource_available"] is False
    assert page["items"][1]["href"] is None
    assert page["next_cursor"]

    rest = service.list_notifications("alice", limit=2, cursor=page["next_cursor"], now=now)
    assert [item["id"] for item in rest["items"]] == [budget_id]
    assert rest["items"][0]["href"] == "/settings/budgets"
    assert rest["unread_count"] == 3
    assert rest["next_cursor"] is None

    budgets = service.list_notifications("alice", kind="budget_alert", now=now)
    assert [item["id"] for item in budgets["items"]] == [budget_id]
    unread = service.list_notifications("alice", unread=True, now=now)
    assert len(unread["items"]) == 3
    assert service.unread_count("bob", now=now) == 1
    with pytest.raises(NotificationNotFound):
        service.mark_read("alice", bob_id, now=now)

    with service._sessions() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(InAppNotification)
                .where(InAppNotification.user_id == "alice")
            )
            == 4
        )


def test_read_and_clear_honor_cutoff_and_do_not_revive_events(tmp_path):
    now = datetime(2026, 11, 1, 12, 0, 0)
    service = NotificationService(f"sqlite:///{tmp_path}/state.sqlite3")
    with service._sessions() as db, db.begin():
        kept = _stage(service, db, created_at=datetime(2026, 11, 1, 11, 0, 0))
        older = _stage(
            service,
            db,
            event_key="task-completed/evaluation/older",
            resource_id="older",
            created_at=datetime(2026, 11, 1, 10, 0, 0),
        )
        kept_id, older_id = kept.id, older.id
    service.mark_read("alice", kept_id, now=now)
    with service._sessions() as db, db.begin():
        again = _stage(service, db)
        assert again.id == kept_id
        assert again.read_at is not None

    cleared = service.clear("alice", before=datetime(2026, 11, 1, 10, 0, 0), now=now)
    assert cleared["updated"] == 1
    assert cleared["cutoff"] == "2026-11-01T10:00:00"
    assert cleared["unread_count"] == 0
    remaining = service.list_notifications("alice", now=now)
    assert [item["id"] for item in remaining["items"]] == [kept_id]
    assert remaining["items"][0]["read"] is True

    with service._sessions() as db, db.begin():
        replayed = _stage(
            service,
            db,
            event_key="task-completed/evaluation/older",
            resource_id="older",
            created_at=datetime(2026, 11, 1, 10, 0, 0),
        )
        assert replayed.id == older_id
        assert replayed.cleared_at is not None
    assert service.list_notifications("alice", now=now)["items"][0]["id"] == kept_id
    assert service.unread_count("alice", now=now) == 0


def test_mark_all_read_stops_at_cutoff(tmp_path):
    now = datetime(2026, 11, 1, 12, 0, 0)
    service = NotificationService(f"sqlite:///{tmp_path}/read-all.sqlite3")
    with service._sessions() as db, db.begin():
        later = _stage(service, db, created_at=datetime(2026, 11, 1, 11, 0, 0))
        earlier = _stage(
            service,
            db,
            event_key="task-completed/evaluation/earlier",
            resource_id="earlier",
            created_at=datetime(2026, 11, 1, 10, 0, 0),
        )
        later_id, earlier_id = later.id, earlier.id
    result = service.mark_all_read("alice", before=datetime(2026, 11, 1, 10, 0, 0), now=now)
    assert result["updated"] == 1
    assert result["unread_count"] == 1
    rows = {
        item["id"]: item["read"] for item in service.list_notifications("alice", now=now)["items"]
    }
    assert rows == {later_id: False, earlier_id: True}
