"""HTTP boundaries for operational monitoring and private task logs."""

import io
import json
import secrets
import time
from unittest.mock import patch
from uuid import UUID

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.requests import ClientDisconnect

from api.auth.config import AuthSettings
from api.config import settings
from api.files.config import FileSettings
from api.main import create_app
from api.monitoring.config import MonitorSettings
from api.routes.monitoring import LogDownloadResponse
from src.cache import LLMResponseCache
from src.task_service import TaskEvent

PASSWORD = "monitor-test-password-long!"
KEY = "private-monitor-key-value"
ADMIN_ROUTES = [
    "/system/health",
    "/health/database",
    "/health/redis",
    "/health/workers",
    "/health/sandbox",
    "/system/workers",
    "/system/resources",
    "/system/status",
    "/system/tasks/running",
    "/system/tasks/queued",
    "/metrics/api-stats",
    "/metrics/performance",
    "/metrics/llm-stats",
    "/metrics/cache-stats",
    "/config/strategies",
    "/config/providers",
    "/config/sandbox",
    "/logs",
]


def headers(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def signup(client, name):
    registered = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.org", "password": PASSWORD},
    )
    assert registered.status_code == 201, registered.text
    response = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "CORS_ORIGINS", ["https://monitor.example"])
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=1000,
        AUTH_PROTECTED_RATE_LIMIT=10000,
    )
    files = FileSettings(
        _env_file=None, UPLOAD_DIR=tmp_path / "uploads", FILE_UPLOAD_RATE_LIMIT=1000
    )
    monitor = MonitorSettings(_env_file=None)
    app = create_app(auth, files, monitor_settings=monitor)
    with TestClient(app) as client:
        admin, user = signup(client, "operator"), signup(client, "admin")
        owner = app.state.auth.store.find_user("operator")["id"]
        monitor.MONITOR_ADMIN_USER_IDS = [UUID(owner)]  # Operator configuration, never HTTP input.
        yield client, admin, user, app, auth, files, monitor


def test_current_role_matches_live_operator_configuration(api):
    client, admin, user, _, _, _, monitor = api
    assert client.get("/api/v1/users/me").status_code == 401
    assert client.get("/api/v1/users/me", headers=headers(user)).json()["data"]["role"] == "user"
    response = client.get("/api/v1/users/me", headers=headers(admin))
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"
    assert response.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/system/status", headers=headers(admin)).status_code == 200
    monitor.MONITOR_ADMIN_USER_IDS = []
    assert client.get("/api/v1/users/me", headers=headers(admin)).json()["data"]["role"] == "user"
    assert client.get("/api/v1/system/status", headers=headers(admin)).status_code == 403


def test_profile_update_cannot_grant_role(api):
    client, _, user, *_ = api
    response = client.patch(
        "/api/v1/users/me", headers=headers(user), json={"username": "admin", "role": "admin"}
    )
    assert response.status_code == 400
    assert client.get("/api/v1/users/me", headers=headers(user)).json()["data"]["role"] == "user"
    assert client.get("/api/v1/system/status", headers=headers(user)).status_code == 403


def make_task(client, tokens):
    key = client.post(
        "/api/v1/api-keys",
        headers=headers(tokens),
        json={"provider": "openai", "key_name": "monitor", "api_key": KEY},
    )
    assert key.status_code == 201
    response = client.post(
        "/api/v1/evaluations",
        headers=headers(tokens),
        json={
            "api_key_id": key.json()["data"]["id"],
            "problem_ids": ["p1"],
            "strategy_names": ["vanilla"],
            "model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["evaluation_id"]


@pytest.mark.parametrize("route", ADMIN_ROUTES)
def test_system_routes_require_authenticated_operator(api, route):
    client, _, user, *_ = api
    assert client.get("/api/v1" + route).status_code == 401
    assert client.get("/api/v1" + route, headers=headers(user)).status_code == 403


def test_operator_identity_is_not_username_or_token_role(api):
    client, admin, user, app, auth, *_ = api
    claims = jwt.decode(
        user["access_token"],
        auth.SECRET_KEY.get_secret_value(),
        algorithms=["HS256"],
        options={"verify_aud": False},
    )
    claims["role"] = "admin"
    forged = jwt.encode(claims, auth.SECRET_KEY.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + forged}).json()[
            "data"
        ]["role"]
        == "user"
    )
    assert client.get(
        "/api/v1/system/health", headers={"Authorization": "Bearer " + forged}
    ).status_code in {401, 403}
    assert (
        client.patch(
            "/api/v1/users/me", headers=headers(admin), json={"username": "renamed_operator"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/system/health", headers=headers(admin)).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "claimed_operator",
                "email": "claim@example.org",
                "password": PASSWORD,
                "role": "admin",
            },
        ).status_code
        == 400
    )
    assert app.state.monitor.settings.is_admin(
        app.state.auth.store.find_user("renamed_operator")["id"]
    )


def test_health_sources_and_safe_admin_configuration(api, monkeypatch):
    client, admin, _, app, auth, files, _ = api
    monkeypatch.setattr(
        app.state.monitor.probes, "sandbox", lambda: {"status": "unavailable", "backend": "docker"}
    )
    public = client.get("/api/v1/health").json()["data"]
    assert public["scope"] == "api_liveness_only" and "checks" not in public
    health = client.get("/api/v1/system/health", headers=headers(admin)).json()["data"]
    assert health["status"] == "partial"
    assert health["checks"]["database"]["status"] == "ok"
    assert health["pending_issues"] == [157]
    business = health["checks"]["database"]["business_database"]
    assert business["migration"]["revisions"] == business["migration"]["expected_heads"]
    assert "experiments" in business["required_tables"]
    assert health["checks"]["redis"]["status"] == "not_checked"
    assert health["checks"]["redis"]["infrastructure_available"] is True
    assert health["checks"]["workers"]["execution_readiness"] == "not_checked"
    assert health["checks"]["workers"]["status"] == "not_checked"
    assert health["checks"]["workers"]["evaluation_worker_implementation"] == "algorithm_harness"
    assert health["checks"]["workers"]["real_evaluation_available"] is None
    assert health["checks"]["sandbox"]["status"] == "not_checked"
    assert (
        client.get("/api/v1/system/health?include_sandbox=true", headers=headers(admin)).json()[
            "data"
        ]["checks"]["sandbox"]["status"]
        == "unavailable"
    )
    assert (
        client.get("/api/v1/system/health?include_sandbox=true", headers=headers(admin)).json()[
            "data"
        ]["status"]
        == "degraded"
    )
    for route in ADMIN_ROUTES:
        response = client.get("/api/v1" + route, headers=headers(admin))
        assert response.status_code == 200, (route, response.text)
        assert str(auth.AUTH_DATABASE_PATH) not in response.text
        assert str(files.UPLOAD_DIR) not in response.text
        assert auth.SECRET_KEY.get_secret_value() not in response.text
        assert auth.ENCRYPTION_KEY.get_secret_value() not in response.text
        assert str(app.state.evaluations.engine.url) not in response.text
    stats = client.get("/api/v1/metrics/api-stats", headers=headers(admin)).json()["data"]
    assert stats["window_complete"] is False and stats["request_count"] is None
    assert stats["retained_sample"]["request_count"] > 0


def test_task_logs_download_redaction_and_active_owner_mapping(api):
    client, admin, user, app, auth, *_ = api
    run_id = make_task(client, user)
    owner = app.state.auth.store.find_user("admin")["id"]
    event = TaskEvent(
        sequence=1,
        run_id=run_id,
        kind="failed",
        state="failed",
        timestamp="2026-10-11T00:00:00Z",
        message=f"Provider returned {KEY}; password=hidden-value; {auth.SECRET_KEY.get_secret_value()}",
    )
    app.state.monitor.record_task_event(event, owner)
    listed = client.get(
        f"/api/v1/logs/tasks/{run_id}?level=ERROR&search=Provider", headers=headers(user)
    )
    assert listed.status_code == 200 and listed.json()["data"]["total"] == 1
    download = client.get(f"/api/v1/logs/download/{run_id}", headers=headers(user))
    assert download.status_code == 200 and "[REDACTED]" in download.text
    for secret in (KEY, "hidden-value", auth.SECRET_KEY.get_secret_value()):
        assert secret not in download.text
        assert secret.encode() not in auth.AUTH_DATABASE_PATH.read_bytes()
    assert download.headers["content-disposition"] == "attachment; filename=task-logs.jsonl"
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    assert all(json.loads(line)["run_id"] == run_id for line in download.text.splitlines())
    for path in (f"/logs/tasks/{run_id}", f"/logs/download/{run_id}"):
        assert client.get("/api/v1" + path, headers=headers(admin)).status_code == 404
        assert client.get("/api/v1" + path).status_code == 401
    assert (
        client.get("/api/v1/logs?level=ERROR", headers=headers(admin)).json()["data"]["total"] == 1
    )
    assert client.delete(f"/api/v1/evaluations/{run_id}", headers=headers(user)).status_code == 204
    assert client.get(f"/api/v1/logs/tasks/{run_id}", headers=headers(user)).status_code == 404


@pytest.mark.parametrize(
    "query",
    [
        "level=TRACE",
        "start=2026-10-11T00:00:00",
        "start=1960-01-01T00:00:00Z",
        "start=2026-10-12T00:00:00Z&end=2026-10-11T00:00:00Z",
        "limit=1001",
        "offset=-1",
    ],
)
def test_invalid_log_filters_are_client_errors(api, query):
    client, admin, *_ = api
    assert client.get("/api/v1/logs?" + query, headers=headers(admin)).status_code == 400


def test_download_exports_retained_rows_over_one_page(api):
    client, _, user, app, *_ = api
    run_id = make_task(client, user)
    owner = app.state.auth.store.find_user("admin")["id"]
    store = app.state.monitor.store
    for i in range(1005):
        store.append_log("WARNING", f"paginated line {i}", user_id=owner, run_id=run_id)
    response = client.get(
        f"/api/v1/logs/download/{run_id}?level=WARNING&limit=1&offset=500", headers=headers(user)
    )
    assert response.status_code == 200
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert len(rows) == 1005 == int(response.headers["x-retained-log-count"])
    assert response.headers["x-exported-log-count"] == "1005"
    assert response.headers["x-log-export-truncated"] == "false"
    assert len({item["id"] for item in rows}) == 1005
    paged = client.get(
        f"/api/v1/logs/tasks/{run_id}?level=WARNING&limit=2&offset=3", headers=headers(user)
    ).json()["data"]
    assert paged["items"] == rows[3:5] and paged["total"] == 1005


def test_real_request_metrics_include_final_413_without_raw_inputs(api):
    client, admin, user, app, auth, files, *_ = api
    files.FILE_UPLOAD_MAX_BYTES = 20
    response = client.post(
        "/api/v1/files/upload?secret=query-private",
        headers={**headers(user), "X-Private": "header-private"},
        files={"file": ("safe.json", b'{"value":"body-private-long-data"}', "application/json")},
    )
    assert response.status_code == 413
    client.get("/api/v1/unknown-path-private?token=query-private")
    with app.state.monitor.store.connection() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM api_monitor_requests")]
        db.execute(
            "UPDATE api_monitor_meta SET value=? WHERE key='started_at'", (time.time() - 120,)
        )
    assert any(row["route"] == "/api/v1/files/upload" and row["status_code"] == 413 for row in rows)
    assert any(row["route"] == "[unmatched]" and row["status_code"] == 404 for row in rows)
    for raw in (
        "query-private",
        "header-private",
        "body-private",
        "unknown-path-private",
        user["access_token"],
    ):
        assert raw.encode() not in auth.AUTH_DATABASE_PATH.read_bytes()
    stats = client.get("/api/v1/metrics/api-stats", headers=headers(admin)).json()["data"]
    assert stats["window_complete"] is True and stats["request_count"] == len(rows)
    assert stats["errors"] == 2 and stats["avg_response_time_ms"] >= 0


def test_monitor_write_failure_preserves_business_response(api, monkeypatch):
    client, admin, _, app, *_ = api

    def fail(*args, **kwargs):
        raise OSError("private storage unavailable")

    monkeypatch.setattr(app.state.monitor.store, "record_request", fail)
    monkeypatch.setattr(app.state.monitor.store, "append_log", fail)
    assert client.get("/api/v1/health").status_code == 200
    assert (
        client.patch(
            "/api/v1/users/me", headers=headers(admin), json={"email": "new@example.org"}
        ).status_code
        == 200
    )


def test_store_survives_restart_with_same_identity_scope(api):
    client, admin, user, app, auth, files, monitor = api
    run_id = make_task(client, user)
    before = client.get(f"/api/v1/logs/tasks/{run_id}", headers=headers(user)).json()["data"]
    restarted = create_app(auth, files, monitor_settings=monitor)
    with TestClient(restarted) as second:
        after = second.get(f"/api/v1/logs/tasks/{run_id}", headers=headers(user))
        assert after.status_code == 200 and after.json()["data"]["items"] == before["items"]
        stats = second.get("/api/v1/metrics/api-stats", headers=headers(admin)).json()["data"]
        assert stats["retained_sample"]["request_count"] > 0
        assert (
            second.get("/api/v1/system/tasks/queued", headers=headers(admin)).json()["data"][
                "total"
            ]
            == 0
        )
        overview = second.get("/api/v1/system/status", headers=headers(admin)).json()["data"]
        assert overview["task_source"] == "persisted_business_evaluations"
        assert overview["task_count"] == 1 and overview["task_counts"] == {"failed": 1}


def test_quotas_are_available_only_for_current_user_and_real_cache_is_opt_in(api):
    client, admin, user, app, _, files, _ = api
    assert client.get("/api/v1/quotas").status_code == 401
    payload = b'{"value":"a small upload"}'
    response = client.post(
        "/api/v1/files/upload",
        headers=headers(user),
        files={"file": ("safe.json", payload, "application/json")},
    )
    assert response.status_code == 201
    mine = client.get("/api/v1/quotas", headers=headers(user)).json()["data"]
    assert mine["storage"]["used_bytes"] == len(payload)
    assert mine["storage"]["limit_bytes"] == files.FILE_MAX_USER_BYTES
    assert mine["protected_requests"]["used"] > 0
    other_id = app.state.auth.store.find_user("admin")["id"]
    other = client.get(
        "/api/v1/quotas/usage", params={"user_id": other_id}, headers=headers(admin)
    ).json()["data"]
    assert other["storage"]["used_bytes"] == 0
    assert other["daily_api_calls"] == {"status": "not_configured", "limit": None, "used": None}
    pending = client.get("/api/v1/metrics/cache-stats", headers=headers(admin)).json()["data"]
    assert pending["status"] == "not_configured"
    cache = LLMResponseCache(str(files.UPLOAD_DIR.parent / "cache-private"))
    cache.get("missing-cache-key")
    app.state.monitor.cache = cache
    data = client.get("/api/v1/metrics/cache-stats", headers=headers(admin)).json()["data"]
    assert data["status"] == "ok" and data["misses"] == 1
    assert str(cache.cache_dir) not in json.dumps(data)


@pytest.mark.asyncio
async def test_download_closes_temporary_file_on_client_disconnect():
    stream = io.BytesIO(b"private retained log\n")
    response = LogDownloadResponse(stream, {})

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        raise OSError("client disconnected")

    with pytest.raises(ClientDisconnect):
        await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
    assert stream.closed


@pytest.mark.parametrize("key_value", ["password", "="])
def test_syntax_shaped_user_key_cannot_expose_other_log_credentials(api, key_value):
    client, _, user, app, auth, *_ = api
    run_id = make_task(client, user)
    owner = app.state.auth.store.find_user("admin")["id"]
    assert (
        client.post(
            "/api/v1/api-keys",
            headers=headers(user),
            json={"provider": "openai", "key_name": "syntax", "api_key": key_value},
        ).status_code
        == 201
    )
    event = TaskEvent(
        sequence=1,
        run_id=run_id,
        kind="failed",
        state="failed",
        timestamp="2026-10-11T00:00:00Z",
        message="password=distinct-private-value",
    )
    app.state.monitor.record_task_event(event, owner)
    response = client.get(f"/api/v1/logs/download/{run_id}?level=ERROR", headers=headers(user))
    assert response.status_code == 200
    assert "distinct-private-value" not in response.text
    assert b"distinct-private-value" not in auth.AUTH_DATABASE_PATH.read_bytes()
    assert "[REDACTED]" in response.text


@pytest.mark.parametrize(
    "origin,status", [("https://monitor.example", 200), ("https://untrusted.example", 400)]
)
def test_cors_preflight_responses_are_included_in_actual_metrics(api, origin, status):
    client, _, _, app, *_ = api
    response = client.options(
        "/api/v1/health", headers={"Origin": origin, "Access-Control-Request-Method": "GET"}
    )
    assert response.status_code == status
    if status == 200:
        assert response.headers["access-control-allow-origin"] == origin
    with app.state.monitor.store.connection() as db:
        rows = db.execute("SELECT * FROM api_monitor_requests WHERE method='OPTIONS'").fetchall()
    assert len(rows) == 1
    assert rows[0]["status_code"] == status
    assert rows[0]["route"] == "[unmatched]" and rows[0]["user_id"] is None


def test_literal_placeholder_inside_known_key_is_removed_from_task_logs(api):
    client, _, user, app, auth, *_ = api
    run_id = make_task(client, user)
    owner = app.state.auth.store.find_user("admin")["id"]
    key_value = "prefix[REDACTED]suffix"
    assert (
        client.post(
            "/api/v1/api-keys",
            headers=headers(user),
            json={"provider": "openai", "key_name": "literal", "api_key": key_value},
        ).status_code
        == 201
    )
    event = TaskEvent(
        sequence=1,
        run_id=run_id,
        kind="failed",
        state="failed",
        timestamp="2026-10-11T00:00:00Z",
        message=f"Provider returned {key_value}",
    )
    app.state.monitor.record_task_event(event, owner)
    response = client.get(f"/api/v1/logs/download/{run_id}?level=ERROR", headers=headers(user))
    assert response.status_code == 200
    assert key_value not in response.text
    assert key_value.encode() not in auth.AUTH_DATABASE_PATH.read_bytes()


def test_persistent_task_pages_have_accurate_full_counts_and_read_only_health(api):
    client, admin, user, app, *_ = api
    first, second = make_task(client, user), make_task(client, admin)
    response = client.get("/api/v1/system/tasks/queued?limit=1&offset=1", headers=headers(admin))
    assert response.status_code == 200
    page = response.json()["data"]
    assert (
        page["source"] == "persisted_business_evaluations"
        and page["execution_backend"] == "unassigned_or_legacy"
    )
    assert page["total"] == 2 and page["counts"] == {"pending": 2} and len(page["items"]) == 1
    assert page["production_queue_configured"] is False
    with patch(
        "api.monitoring.probes.EvaluationService", side_effect=AssertionError("no recovery")
    ):
        for _ in range(2):
            assert (
                client.get("/api/v1/health/database", headers=headers(admin)).json()["data"][
                    "business_database"
                ]["status"]
                == "ok"
            )
            overview = client.get("/api/v1/system/status", headers=headers(admin)).json()["data"]
            assert overview["task_count"] == 2 and overview["task_counts"] == {"pending": 2}
    assert (
        app.state.evaluations.get_evaluation(
            first, app.state.auth.store.find_user("admin")["id"]
        ).status
        == "pending"
    )
    assert (
        app.state.evaluations.get_evaluation(
            second, app.state.auth.store.find_user("operator")["id"]
        ).status
        == "pending"
    )
    assert (
        client.get("/api/v1/system/tasks/queued?limit=1001", headers=headers(admin)).status_code
        == 400
    )
    assert (
        client.get("/api/v1/system/tasks/running?offset=-1", headers=headers(admin)).status_code
        == 400
    )


def test_actual_queries_errors_and_database_failure_are_explicit_without_secrets(api):
    client, admin, user, app, *_ = api
    make_task(client, user)
    with pytest.raises(Exception):
        with app.state.evaluations.engine.connect() as connection:
            connection.execute(
                text("SELECT :value FROM missing_private_table"),
                {"value": "query-private-credential"},
            )
    data = client.get("/api/v1/metrics/performance", headers=headers(admin)).json()["data"][
        "database_queries"
    ]
    assert data["status"] == "ok" and data["scope"] == "bound_business_engine_current_process"
    assert data["window_complete"] is False and data["query_count"] is None
    assert data["retained_sample"]["errors"] == 1 and data["retained_sample"]["query_count"] >= 2
    assert "query-private-credential" not in json.dumps(
        data
    ) and "missing_private_table" not in json.dumps(data)
    with patch.object(
        app.state.evaluations.engine,
        "connect",
        side_effect=RuntimeError("password=private-db-secret"),
    ):
        health = client.get("/api/v1/system/health", headers=headers(admin)).json()["data"]
        snapshot = client.get("/api/v1/system/tasks/queued", headers=headers(admin)).json()["data"]
    assert (
        health["status"] == "degraded"
        and health["checks"]["database"]["business_database"]["status"] == "unavailable"
    )
    assert (
        snapshot["status"] == "unavailable"
        and snapshot["total"] is None
        and snapshot["items"] is None
        and snapshot["counts"] is None
    )
    assert "private-db-secret" not in json.dumps([health, snapshot])


def test_database_config_positional_argument_and_metrics_lifecycle(tmp_path):
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )
    files = FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads")
    app = create_app(
        auth,
        files,
        f"sqlite:///{tmp_path / 'business.sqlite3'}",
        monitor_settings=MonitorSettings(_env_file=None),
    )
    with TestClient(app):
        collector = app.state.monitor.database_metrics
        engine = app.state.evaluations.engine
        assert collector.stats()["collection_active"] is True
    assert collector.stats()["collection_active"] is False
    before = collector.stats()["retained_sample"]["query_count"]
    with engine.connect() as connection:
        assert connection.execute(text("SELECT 7")).scalar() == 7
    assert collector.stats()["retained_sample"]["query_count"] == before
    engine.dispose()
