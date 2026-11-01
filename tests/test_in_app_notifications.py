"""In-app notification storage, delivery and API (issue #328)."""

import secrets
import uuid
from datetime import datetime
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select
from sqlalchemy.exc import IntegrityError

from api.auth.config import AuthSettings
from api.db import (
    ABTest,
    AsyncTask,
    BenchmarkRun,
    BenchmarkSuite,
    Evaluation,
    Experiment,
    InAppNotification,
    downgrade,
    make_engine,
    make_session_factory,
    offline_upgrade_sql,
    run_migrations,
)
from api.files.config import FileSettings
from api.main import create_app
from api.services.in_app_notification_service import NotificationNotFound, NotificationService

PASSWORD = "a-long-test-password-!"


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


def _login(client: TestClient, username: str) -> tuple[dict[str, str], str]:
    client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": f"{username}@example.org",
            "password": PASSWORD,
        },
    )
    token = client.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    ).json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    user_id = client.get("/api/v1/users/me", headers=headers).json()["data"]["id"]
    return headers, user_id


def test_notification_routes_return_only_the_current_user(tmp_path):
    app = create_app(
        auth_settings=AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        ),
        file_settings=FileSettings(UPLOAD_DIR=tmp_path / "uploads"),
    )
    with TestClient(app) as client:
        alice, alice_id = _login(client, "alice")
        bob, _bob_id = _login(client, "bob")
        from src.task_manager import TaskManager

        with app.state.notifications._sessions() as db, db.begin():
            task = _running_task("evaluation", "ev-1")
            task.user_id = alice_id
            db.add(Evaluation(id="ev-1", user_id=alice_id, async_task_id=task.id))
            db.add(task)
            task_id = task.id
        with app.state.notifications._sessions() as db:
            TaskManager(db).update_task_status(task_id, "completed")
        note_id = app.state.notifications.list_notifications(alice_id)["items"][0]["id"]
        listed = client.get("/api/v1/notifications", headers=alice)
        assert listed.status_code == 200, listed.text
        body = listed.json()["data"]
        assert body["unread_count"] == 1
        assert body["items"][0]["id"] == note_id
        assert body["items"][0]["href"] == "/evaluations/ev-1"
        counted = client.get("/api/v1/notifications/unread-count", headers=alice)
        assert counted.json()["data"]["unread_count"] == 1
        assert client.get("/api/v1/notifications", headers=bob).json()["data"]["items"] == []
        missing = client.post(f"/api/v1/notifications/{note_id}/read", headers=bob)
        assert missing.status_code == 404
        read = client.post(f"/api/v1/notifications/{note_id}/read", headers=alice)
        assert read.status_code == 200
        assert read.json()["data"]["read"] is True
        assert (
            client.get("/api/v1/notifications/unread-count", headers=alice).json()["data"][
                "unread_count"
            ]
            == 0
        )
        # A fresh login observes the persisted read and clear state.
        alice_again, _ = _login(client, "alice")
        assert (
            client.get("/api/v1/notifications", headers=alice_again).json()["data"]["items"][0][
                "read"
            ]
            is True
        )
        cleared = client.post("/api/v1/notifications/clear", headers=alice_again)
        assert cleared.json()["data"]["updated"] == 1
        assert client.get("/api/v1/notifications", headers=alice).json()["data"]["items"] == []
        with app.state.notifications._sessions() as db:
            TaskManager(db).update_task_status(task_id, "completed")
        assert (
            client.get("/api/v1/notifications", headers=alice_again).json()["data"]["items"] == []
        )


def test_notification_operations_are_documented():
    schema = create_app().openapi()
    assert schema["info"]["version"] == "1.5.0"
    paths = schema["paths"]
    for path in (
        "/api/v1/notifications",
        "/api/v1/notifications/unread-count",
        "/api/v1/notifications/read-all",
        "/api/v1/notifications/clear",
        "/api/v1/notifications/{notification_id}/read",
    ):
        operation = next(iter(paths[path].values()))
        assert "认证" in operation["description"], path
        assert "未读" in operation["description"] or "通知" in operation["description"]
    example = paths["/api/v1/notifications"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]["data"]
    assert example["unread_count"] == 1
    assert example["items"][0]["kind"] == "task_completed"


def _running_task(task_type: str, entity_id: str) -> AsyncTask:
    return AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id=str(uuid.uuid4()),
        task_type=task_type,
        entity_id=entity_id,
        user_id="alice",
        status="running",
    )


def test_completion_notifies_each_task_once_and_skips_history(tmp_path):
    from src.task_manager import TaskManager

    url = f"sqlite:///{tmp_path}/completion.sqlite3"
    run_migrations(url)
    factory = make_session_factory(make_engine(url))
    with factory() as db, db.begin():
        db.add(BenchmarkSuite(id="suite", user_id="alice", name="suite"))
        db.flush()
        db.add(Evaluation(id="ev", user_id="alice", completed_count=2, problem_count=4))
        db.add(Experiment(id="exp", user_id="alice", config={}))
        db.add(BenchmarkRun(id="run", suite_id="suite", user_id="alice", model="m", config={}))
        db.add(ABTest(id="ab", user_id="alice", config={}))
        db.add(Evaluation(id="old", user_id="alice", status="completed", problem_count=1))
        tasks = [
            _running_task("evaluation", "ev"),
            _running_task("experiment", "exp"),
            _running_task("benchmark", "run"),
            _running_task("ab_test", "ab"),
        ]
        old = _running_task("evaluation", "old")
        old.status = "completed"
        db.add_all([*tasks, old])
        task_ids = [task.id for task in tasks]
        old_id = old.id
    with factory() as db:
        manager = TaskManager(db)
        for task_id in task_ids:
            manager.update_task_status(task_id, "completed")
        manager.update_task_status(old_id, "completed")
    service = NotificationService(url)
    page = service.list_notifications("alice")
    assert sorted(item["href"] for item in page["items"]) == [
        "/ab-tests/ab",
        "/benchmarks/suite",
        "/evaluations/ev",
        "/experiments/exp",
    ]
    assert page["unread_count"] == 4
    evaluation = next(item for item in page["items"] if item["href"] == "/evaluations/ev")
    assert evaluation["params"]["completed_count"] == 2
    assert evaluation["params"]["total_count"] == 4
    service.mark_read("alice", evaluation["id"])
    with factory() as db:
        TaskManager(db).update_task_status(task_ids[0], "completed")
    again = service.list_notifications("alice", limit=10)
    assert len(again["items"]) == 4
    assert next(item for item in again["items"] if item["id"] == evaluation["id"])["read"] is True
    assert service.unread_count("alice") == 3


def test_interrupted_completion_retry_creates_one_notification(tmp_path):
    from src.task_manager import TaskManager

    url = f"sqlite:///{tmp_path}/retry.sqlite3"
    run_migrations(url)
    factory = make_session_factory(make_engine(url))
    with factory() as db, db.begin():
        task = _running_task("evaluation", "ev")
        db.add(
            Evaluation(
                id="ev", user_id="alice", async_task_id=task.id, completed_count=1, problem_count=1
            )
        )
        db.add(task)
        task_id = task.id
    real_commit = TaskManager._commit

    def fail_once(self):
        if not getattr(fail_once, "used", False):
            fail_once.used = True
            self.db.rollback()
            raise RuntimeError("interrupted")
        return real_commit(self)

    with factory() as db, pytest.raises(RuntimeError, match="interrupted"):
        with patch.object(TaskManager, "_commit", fail_once):
            TaskManager(db).update_task_status(task_id, "completed")
    with factory() as db:
        assert db.get(Evaluation, "ev").status != "completed"
        assert db.get(AsyncTask, task_id).status == "running"
        assert db.scalar(select(func.count()).select_from(InAppNotification)) == 0
        TaskManager(db).update_task_status(task_id, "completed")
    with factory() as db:
        assert db.get(Evaluation, "ev").status == "completed"
        assert db.get(AsyncTask, task_id).status == "completed"
    notes = NotificationService(url).list_notifications("alice")
    assert len(notes["items"]) == 1
    assert notes["items"][0]["href"] == "/evaluations/ev"


def test_pagination_preserves_subsecond_cursor_order(tmp_path):
    service = NotificationService(f"sqlite:///{tmp_path}/cursor.sqlite3")
    now = datetime(2026, 11, 1, 12, 0, 0, 900000)
    with service._sessions() as db, db.begin():
        for index, micros in enumerate((100000, 200000, 200000)):
            _stage(
                service,
                db,
                event_key=f"event/{index}",
                created_at=datetime(2026, 11, 1, 12, 0, 0, micros),
            )
    seen = []
    cursor = None
    while True:
        page = service.list_notifications("alice", limit=1, cursor=cursor, now=now)
        seen.extend(item["id"] for item in page["items"])
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert len(seen) == len(set(seen)) == 3


@pytest.mark.parametrize("operation", ["clear", "mark_all_read"])
def test_batch_uses_precise_list_snapshot_cutoff(tmp_path, operation):
    service = NotificationService(f"sqlite:///{tmp_path}/cutoff.sqlite3")
    snapshot = datetime(2026, 11, 1, 12, 0, 0, 500000)
    with service._sessions() as db, db.begin():
        old = _stage(service, db, created_at=datetime(2026, 11, 1, 12, 0, 0, 100000))
        old_id = old.id
    page = service.list_notifications("alice", now=snapshot)
    with service._sessions() as db, db.begin():
        new = _stage(
            service, db, event_key="event/new", created_at=datetime(2026, 11, 1, 12, 0, 0, 600000)
        )
        new_id = new.id
    result = getattr(service, operation)(
        "alice",
        before=datetime.fromisoformat(page["server_time"]),
        now=datetime(2026, 11, 1, 12, 0, 1),
    )
    assert result["updated"] == 1
    remaining = {
        item["id"]: item for item in service.list_notifications("alice", now=snapshot)["items"]
    }
    assert remaining[new_id]["read"] is False
    if operation == "clear":
        assert old_id not in remaining
    else:
        assert remaining[old_id]["read"] is True


def test_concurrent_delivery_preserves_one_event_and_clear_tombstone(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    service = NotificationService(f"sqlite:///{tmp_path}/concurrent.sqlite3")
    barrier = Barrier(2)

    def deliver():
        barrier.wait(timeout=5)
        with service._sessions() as db, db.begin():
            return _stage(service, db).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: deliver(), range(2)))
    assert ids[0] == ids[1]
    now = datetime(2026, 11, 1, 12)
    assert service.list_notifications("alice", now=now)["unread_count"] == 1
    service.clear("alice", now=now)
    barrier.reset()
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(lambda _: deliver(), range(2))) == ids
    assert service.list_notifications("alice", now=now)["items"] == []


@pytest.mark.parametrize("operation", ["clear", "mark_all_read"])
def test_batch_excludes_notification_committed_by_another_worker(tmp_path, operation):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    service = NotificationService(f"sqlite:///{tmp_path}/batch-race.sqlite3")
    snapshot = datetime(2026, 11, 1, 12, 0, 0, 500000)
    with service._sessions() as db, db.begin():
        _stage(service, db)
    page = service.list_notifications("alice", now=snapshot)
    inserted, updating, release = Event(), Event(), Event()

    def observe_update(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("UPDATE in_app_notifications"):
            updating.set()

    event.listen(service._engine, "before_cursor_execute", observe_update)

    def deliver():
        with service._sessions() as db, db.begin():
            row = _stage(
                service,
                db,
                event_key="event/new",
                created_at=datetime(2026, 11, 1, 12, 0, 0, 600000),
            )
            inserted.set()
            assert release.wait(5)
            return row.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(deliver)
        assert inserted.wait(5)
        try:
            batch = pool.submit(
                getattr(service, operation),
                "alice",
                before=datetime.fromisoformat(page["server_time"]),
                now=datetime(2026, 11, 1, 12, 0, 1),
            )
            assert updating.wait(5)
        finally:
            release.set()
        new_id = future.result()
        assert batch.result()["updated"] == 1
    notes = service.list_notifications("alice", now=datetime(2026, 11, 1, 12, 0, 1))["items"]
    assert next(item for item in notes if item["id"] == new_id)["read"] is False


def test_notification_insert_rolls_back_with_outer_transaction(tmp_path):
    service = NotificationService(f"sqlite:///{tmp_path}/rollback.sqlite3")
    with pytest.raises(RuntimeError, match="interrupted"):
        with service._sessions() as db, db.begin():
            _stage(service, db)
            raise RuntimeError("interrupted")
    assert service.list_notifications("alice", now=datetime(2026, 11, 1, 12))["items"] == []
