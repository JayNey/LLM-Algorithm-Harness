"""In-app notification storage, delivery and API (issue #328)."""

from datetime import datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from api.db import (
    InAppNotification,
    downgrade,
    make_engine,
    make_session_factory,
    offline_upgrade_sql,
    run_migrations,
)


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
