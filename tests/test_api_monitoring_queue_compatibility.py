"""HTTP regressions for monitoring coexistence with the Celery task API."""

import secrets
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import event, select, update

from api.auth.config import AuthSettings
from api.db.models import AsyncTask, Evaluation
from api.files.config import FileSettings
from api.main import create_app
from api.monitoring.config import MonitorSettings

PASSWORD = "queue-monitor-password-long!"
PRIVATE_VALUE = "queue-monitor-private-value"


def make_app(root):
    return create_app(
        AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=root / "auth.sqlite3",
            AUTH_RATE_LIMIT=1000,
            AUTH_PROTECTED_RATE_LIMIT=10000,
        ),
        FileSettings(
            _env_file=None,
            UPLOAD_DIR=root / "uploads",
            FILE_UPLOAD_RATE_LIMIT=1000,
        ),
        database_url=f"sqlite:///{root / 'business.sqlite3'}",
        monitor_settings=MonitorSettings(_env_file=None),
    )


def signup(client, name):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.org", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    owner = response.json()["data"]["id"]
    login = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    assert login.status_code == 200, login.text
    return owner, {"Authorization": "Bearer " + login.json()["data"]["access_token"]}


def create_queue_task(client, credentials, entity_id=None):
    entity_id = entity_id or str(uuid4())
    broker_id = "broker-" + str(uuid4())
    with patch("src.task_manager.celery_app.send_task") as send:
        send.return_value = SimpleNamespace(id=broker_id)
        response = client.post(
            "/api/v1/tasks",
            headers=credentials,
            json={
                "task_type": "evaluation",
                "entity_id": entity_id,
                "celery_task_name": "src.tasks.evaluation.run_evaluation_task",
                "celery_task_args": [entity_id],
            },
        )
    assert response.status_code == 201, response.text
    send.assert_called_once_with(
        "src.tasks.evaluation.run_evaluation_task", args=(entity_id,), kwargs={}
    )
    return response.json()["data"]["id"]


def create_legacy_evaluation(client, credentials):
    key = client.post(
        "/api/v1/api-keys",
        headers=credentials,
        json={"provider": "openai", "key_name": "queue-monitor", "api_key": PRIVATE_VALUE},
    )
    assert key.status_code == 201, key.text
    response = client.post(
        "/api/v1/evaluations",
        headers=credentials,
        json={
            "api_key_id": key.json()["data"]["id"],
            "strategy_names": ["vanilla"],
            "problem_ids": ["p1", "p2"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["evaluation_id"]


@pytest.fixture
def api(tmp_path):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        owner, admin = signup(client, "operator")
        _, user = signup(client, "ordinary")
        app.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(owner)]
        yield app, client, admin, user


@pytest.mark.parametrize("endpoint", ["running", "queued"])
def test_async_source_requires_authentication_and_server_selected_admin(api, endpoint):
    _, client, _, user = api
    path = f"/api/v1/system/tasks/{endpoint}?task_source=async_task"
    assert client.get(path).status_code == 401
    assert client.get(path, headers=user).status_code == 403


@pytest.mark.parametrize("endpoint", ["running", "queued"])
@pytest.mark.parametrize(
    "query",
    [
        "task_source=unknown-source",
        "task_source=async_task&limit=0",
        "task_source=async_task&limit=1001",
        "task_source=async_task&offset=-1",
        "task_source=async_task&offset=100001",
        "task_source=async_task&limit=abc",
    ],
)
def test_invalid_source_and_page_parameters_return_400(api, endpoint, query):
    _, client, admin, _ = api
    response = client.get(f"/api/v1/system/tasks/{endpoint}?{query}", headers=admin)
    assert response.status_code == 400


def test_actual_task_and_legacy_routes_coexist_and_linked_tasks_are_not_double_counted(api):
    app, client, admin, _ = api
    legacy_id = create_legacy_evaluation(client, admin)
    linked_id = create_legacy_evaluation(client, admin)
    async_id = create_queue_task(client, admin, linked_id)
    with app.state.task_engine.begin() as connection:
        connection.execute(
            update(Evaluation).where(Evaluation.id == linked_id).values(async_task_id=async_id)
        )
    queued = "/api/v1/system/tasks/queued"
    legacy = client.get(queued, headers=admin).json()["data"]
    queue = client.get(queued + "?task_source=async_task", headers=admin).json()["data"]
    assert legacy["task_source"] == "legacy_evaluation"
    assert legacy["total"] == 1 and legacy["counts"] == {"pending": 1}
    assert [item["task_id"] for item in legacy["items"]] == [legacy_id]
    assert queue["task_source"] == "async_task"
    assert queue["total"] == 1 and queue["counts"] == {"pending": 1}
    assert [item["task_id"] for item in queue["items"]] == [async_id]
    assert queue["evaluation_worker_implementation"] == "mock"
    assert queue["real_evaluation_available"] is False
    status = client.get("/api/v1/system/status", headers=admin).json()["data"]
    assert status["task_counts"] == {"pending": 1} and status["task_count"] == 1
    assert status["async_task_counts"] == {"pending": 1} and status["async_task_count"] == 1
    assert status["task_source"] == "persisted_business_evaluations"
    assert status["async_task_source"] == "persisted_async_tasks"
    # Existing legacy API records remain independently addressable.
    assert client.get(f"/api/v1/evaluations/{linked_id}", headers=admin).status_code == 200
    tasks = client.get("/api/v1/tasks", headers=admin)
    assert tasks.status_code == 200
    assert [item["id"] for item in tasks.json()["data"]["items"]] == [async_id]


def test_async_progress_is_safe_and_does_not_claim_real_worker_results(api):
    app, client, admin, _ = api
    valid_id = create_queue_task(client, admin)
    invalid_id = create_queue_task(client, admin)
    with app.state.task_engine.begin() as connection:
        connection.execute(
            update(AsyncTask)
            .where(AsyncTask.id == valid_id)
            .values(
                status="running",
                progress={
                    "current": 1,
                    "total": 2,
                    "message": PRIVATE_VALUE,
                    "params": {"password": PRIVATE_VALUE},
                },
                error_message=PRIVATE_VALUE,
            )
        )
        connection.execute(
            update(AsyncTask)
            .where(AsyncTask.id == invalid_id)
            .values(status="running", progress={"current": True, "total": 2})
        )
    response = client.get("/api/v1/system/tasks/running?task_source=async_task", headers=admin)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2 and data["counts"] == {"running": 2}
    items = {item["task_id"]: item for item in data["items"]}
    assert items[valid_id]["completed"] == 1 and items[valid_id]["total"] == 2
    assert items[invalid_id]["completed"] is None and items[invalid_id]["total"] is None
    assert data["real_evaluation_available"] is False
    assert data["execution_backend"] == "celery"
    for forbidden in (PRIVATE_VALUE, "params", "error_message", "celery_task_id", "progress"):
        assert forbidden not in response.text
    page = client.get(
        "/api/v1/system/tasks/running?task_source=async_task&limit=1&offset=1", headers=admin
    ).json()["data"]
    assert page["total"] == 2 and page["counts"] == {"running": 2}
    assert len(page["items"]) == 1


def test_monitoring_does_not_poll_queue_or_modify_business_records(api):
    app, client, admin, _ = api
    legacy_id = create_legacy_evaluation(client, admin)
    async_id = create_queue_task(client, admin)
    statements = []

    def records():
        with app.state.task_engine.connect() as connection:
            return (
                connection.execute(
                    select(
                        AsyncTask.id,
                        AsyncTask.status,
                        AsyncTask.progress,
                        AsyncTask.updated_at,
                    )
                ).all(),
                connection.execute(
                    select(
                        Evaluation.id,
                        Evaluation.status,
                        Evaluation.completed_count,
                        Evaluation.updated_at,
                    )
                ).all(),
            )

    def observe(_conn, _cursor, statement, _params, _context, _many):
        statements.append(statement)

    before = records()
    engines = (app.state.task_engine, app.state.evaluations.engine)
    for engine in engines:
        event.listen(engine, "before_cursor_execute", observe)
    try:
        with ExitStack() as stack:
            for target in (
                "src.task_manager.TaskManager.get_task",
                "src.task_manager.celery_app.send_task",
                "src.task_manager.celery_app.AsyncResult",
                "src.task_manager.celery_app.control.inspect",
                "src.task_manager.celery_app.connection_for_read",
                "redis.Redis.from_url",
                "redis.Redis.ping",
            ):
                stack.enter_context(patch(target, side_effect=AssertionError("queue polled")))
            for endpoint in (
                "/system/tasks/queued?task_source=async_task",
                "/system/tasks/running?task_source=async_task",
                "/system/tasks/queued",
                "/system/status",
                "/system/health",
                "/health/redis",
                "/health/workers",
            ):
                assert client.get("/api/v1" + endpoint, headers=admin).status_code == 200
    finally:
        for engine in engines:
            event.remove(engine, "before_cursor_execute", observe)
    assert records() == before
    unexpected = [
        statement
        for statement in statements
        if not statement.lstrip().upper().startswith(("SELECT", "BEGIN"))
        and statement != 'PRAGMA main.table_info("alembic_version")'
    ]
    assert statements and not unexpected, unexpected
    assert before[0][0].id == async_id and before[1][0].id == legacy_id


def test_simultaneous_apps_keep_http_tasks_and_monitoring_on_each_actual_engine(tmp_path):
    first, second = make_app(tmp_path / "one"), make_app(tmp_path / "two")
    with TestClient(first) as one:
        owner_one, credentials_one = signup(one, "operator")
        first.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(owner_one)]
        one_id = create_queue_task(one, credentials_one)
        with TestClient(second) as two:
            owner_two, credentials_two = signup(two, "operator")
            second.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(owner_two)]
            two_id = create_queue_task(two, credentials_two)
            after_second_start_id = create_queue_task(one, credentials_one)
            assert first.state.monitor.task_engine is first.state.task_engine
            assert second.state.monitor.task_engine is second.state.task_engine
            assert first.state.task_engine is not second.state.task_engine
            list_one = one.get("/api/v1/tasks", headers=credentials_one).json()["data"]
            list_two = two.get("/api/v1/tasks", headers=credentials_two).json()["data"]
            assert {item["id"] for item in list_one["items"]} == {one_id, after_second_start_id}
            assert {item["id"] for item in list_two["items"]} == {two_id}
            for client, credentials, expected in (
                (one, credentials_one, {one_id, after_second_start_id}),
                (two, credentials_two, {two_id}),
            ):
                data = client.get(
                    "/api/v1/system/tasks/queued?task_source=async_task", headers=credentials
                ).json()["data"]
                assert data["total"] == len(expected)
                assert {item["task_id"] for item in data["items"]} == expected
            assert one.get(f"/api/v1/tasks/{two_id}", headers=credentials_one).status_code == 404
            assert two.get(f"/api/v1/tasks/{one_id}", headers=credentials_two).status_code == 404
        # The first app continues serving its own database after the later app shuts down.
        assert one.get("/api/v1/tasks", headers=credentials_one).json()["data"]["total"] == 2


def test_lifespan_closes_monitor_then_services_and_disposes_actual_task_engine(tmp_path):
    app = make_app(tmp_path)
    calls = []
    with ExitStack() as lifetime:
        client = lifetime.enter_context(TestClient(app))
        owner, credentials = signup(client, "operator")
        app.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(owner)]
        create_queue_task(client, credentials)
        monitor, evaluation, engine = (
            app.state.monitor,
            app.state.evaluations,
            app.state.task_engine,
        )
        original_monitor_close = monitor.close
        original_evaluation_close = evaluation.close
        original_dispose = engine.dispose

        def close_monitor():
            calls.append("monitor")
            original_monitor_close()

        def close_evaluation():
            calls.append("evaluation")
            original_evaluation_close()

        def dispose_engine():
            calls.append("task_engine")
            original_dispose()

        monitor.close = close_monitor
        evaluation.close = close_evaluation
        engine.dispose = dispose_engine
    assert calls == ["monitor", "evaluation", "task_engine"]
