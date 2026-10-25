"""Public readiness boundaries and bounded database observations."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import create_app


def healthy():
    return {
        "status": "ok",
        "authentication": {"status": "ok"},
        "files": {"status": "ok"},
        "business_database": {"status": "ok", "migration": {"status": "ok"}},
    }


def checker(probe, **kwargs):
    from api.monitoring.readiness import ReadinessCheck

    return ReadinessCheck(probe, **kwargs)


def test_public_http_minimal_contract():
    from api.monitoring.readiness import ReadinessCheck

    app = create_app()
    result = healthy()
    app.state.monitor = SimpleNamespace(readiness=ReadinessCheck(lambda: result, ttl=0))
    client = TestClient(app)
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert response.headers["cache-control"] == "no-store"
    result["authentication"]["status"] = "unavailable"
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert client.get("/api/v1/health").status_code == 200
    operation = app.openapi()["paths"]["/api/v1/health/ready"]["get"]
    assert not operation.get("security")
    assert "503" in operation["responses"]
    assert operation["responses"]["503"]["content"]["application/json"]["schema"] == (
        operation["responses"]["200"]["content"]["application/json"]["schema"]
    )


@pytest.mark.parametrize("component", ["authentication", "files", "business_database"])
@pytest.mark.parametrize("status", ["unavailable", "unknown", "not_checked", None])
def test_missing_or_failed_component_never_ready(component, status):
    result = healthy()
    result[component] = {"status": status}
    assert checker(lambda: result).check() is False


def test_migration_and_malformed_observations_fail_closed():
    result = healthy()
    result["business_database"]["migration"]["status"] = "mismatch"
    for observation in (result, {}, None, {"status": "ok"}):
        assert checker(lambda: observation).check() is False


def test_probe_exception_is_unready():
    def broken():
        raise RuntimeError("password=private-database")

    assert checker(broken).check() is False


def test_success_and_failure_cache_expire_without_stale_success():
    result = healthy()
    check = checker(lambda: result, ttl=0.03)
    assert check.check() is True
    result["files"]["status"] = "unavailable"
    assert check.check() is True
    time.sleep(0.05)
    assert check.check() is False
    result["files"]["status"] = "ok"
    assert check.check() is False
    time.sleep(0.05)
    assert check.check() is True
    assert checker(lambda: {}).check() is False


def test_concurrent_calls_share_probe():
    release, entered = threading.Event(), threading.Event()
    calls = []

    def probe():
        calls.append(1)
        entered.set()
        release.wait(1)
        return healthy()

    check = checker(probe)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = [pool.submit(check.check) for _ in range(8)]
        assert entered.wait(1)
        release.set()
        assert all(result.result() is True for result in results)
    assert len(calls) == 1


def test_timeout_discards_late_result_and_bounds_background_work():
    release, finished = threading.Event(), threading.Event()
    calls = []

    def probe():
        calls.append(1)
        release.wait(1)
        finished.set()
        return healthy()

    check = checker(probe, timeout=0.03, ttl=0.02)
    try:
        started = time.monotonic()
        assert check.check() is False
        assert time.monotonic() - started < 0.3
        time.sleep(0.04)
        for _ in range(10):
            assert check.check() is False
        assert len(calls) == 1
    finally:
        release.set()
    assert finished.wait(1)
    time.sleep(0.04)
    assert check.check() is True
    assert len(calls) == 2


@pytest.fixture
def live_api(tmp_path):
    import secrets

    from cryptography.fernet import Fernet

    from api.auth.config import AuthSettings
    from api.files.config import FileSettings
    from api.monitoring.config import MonitorSettings

    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )
    app = create_app(
        auth,
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        monitor_settings=MonitorSettings(_env_file=None),
    )
    with TestClient(app) as client:
        app.state.monitor.readiness = checker(lambda: app.state.monitor.probes.database(), ttl=0)
        yield client, app


@pytest.mark.parametrize("failure", ["auth", "files", "business", "migration"])
def test_real_database_schema_and_migration_failures(live_api, failure, monkeypatch):
    from sqlalchemy import text

    client, app = live_api

    def unwanted(*args, **kwargs):
        raise AssertionError("Optional dependency must not be probed")

    for name in ("redis", "workers", "sandbox"):
        monkeypatch.setattr(app.state.monitor.probes, name, unwanted)
    assert client.get("/api/v1/health/ready").status_code == 200
    if failure in ("auth", "files"):
        table = "auth_users" if failure == "auth" else "api_file_objects"
        with app.state.auth.store.connection() as db:
            db.execute(f"DROP TABLE {table}")
    else:
        with app.state.evaluations.engine.begin() as db:
            if failure == "migration":
                db.execute(text("DELETE FROM alembic_version"))
            else:
                db.execute(text("DROP TABLE evaluations"))
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not_ready"}
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.asyncio
async def test_readiness_bypasses_saturated_business_threadpool():
    import asyncio

    import anyio
    import httpx

    app = create_app()
    app.state.monitor = SimpleNamespace(readiness=checker(healthy))
    release, entered = threading.Event(), threading.Event()
    limiter = anyio.to_thread.current_default_thread_limiter()
    previous = limiter.total_tokens
    limiter.total_tokens = 1

    def occupy():
        entered.set()
        release.wait(3)

    busy = asyncio.create_task(anyio.to_thread.run_sync(occupy))
    try:
        while not entered.is_set():
            await asyncio.sleep(0.001)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await asyncio.wait_for(client.get("/api/v1/health/ready"), 0.5)
            assert response.status_code == 200
            assert response.json() == {"status": "ready"}
    finally:
        release.set()
        await busy
        limiter.total_tokens = previous


def test_expired_request_cannot_start_or_publish_probe():
    calls = []

    def probe():
        calls.append(1)
        return healthy()

    check = checker(probe)
    assert check.check(deadline=time.monotonic() - 1) is False
    assert calls == []
    assert check.check() is True


def test_request_deadline_discards_late_success():
    def probe():
        time.sleep(0.05)
        return healthy()

    check = checker(probe)
    assert check.check(deadline=time.monotonic() + 0.01) is False
    time.sleep(0.1)
    assert check.check() is False
