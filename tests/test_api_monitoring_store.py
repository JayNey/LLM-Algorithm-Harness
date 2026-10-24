"""Persistent coverage, bounded logs, and direct ASGI request measurement."""

import asyncio
import io
import json
import multiprocessing
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

import api.middleware.logging as logging_module
import api.monitoring.store as store_module
from api.auth.middleware import AuthBoundaryMiddleware
from api.auth.store import AuthStore
from api.middleware.logging import LoggingMiddleware, setup_logging_middleware
from api.monitoring.store import MonitorStore


@pytest.fixture
def clock(monkeypatch):
    value = [100.0]
    monkeypatch.setattr(store_module, "time", SimpleNamespace(time=lambda: value[0]))
    return value


def test_llm_calls_persist_across_connections_without_request_payloads(tmp_path):
    path = tmp_path / "auth.sqlite3"
    writer = MonitorStore(AuthStore(path))
    empty = writer.llm_stats()
    assert empty["total_calls"] == 0
    assert empty["success_rate"] is None and empty["avg_latency_ms"] is None
    assert empty["started_at"] is None
    writer.record_llm_call(True, 125.0)
    MonitorStore(AuthStore(path)).record_llm_call(False, 375.0)
    stats = MonitorStore(AuthStore(path)).llm_stats()
    assert stats["total_calls"] == 2
    assert stats["successful_calls"] == stats["failed_calls"] == 1
    assert stats["success_rate"] == 0.5 and stats["avg_latency_ms"] == 250.0
    assert stats["started_at"] > 0
    assert stats["collection_mode"] == "best_effort"
    assert stats["scope"] == "recorded_completed_attempts_shared_auth_database"
    with writer.connection() as db:
        rows = db.execute(
            "SELECT key,value FROM api_monitor_meta WHERE key LIKE 'llm_%'"
        ).fetchall()
        assert {row[0] for row in rows} >= {
            "llm_total_calls",
            "llm_successful_calls",
            "llm_failed_calls",
            "llm_duration_ms",
            "llm_started_at",
        }
        assert all(isinstance(row[1], (int, float)) for row in rows)
        assert db.execute("SELECT COUNT(*) FROM api_monitor_logs").fetchone()[0] == 0
        calls = db.execute("SELECT * FROM api_monitor_llm_calls").fetchall()
        assert len(calls) == 2
        assert all(isinstance(value, (int, float)) for call in calls for value in call)


def test_llm_concurrent_writers_do_not_lose_updates(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda i: store.record_llm_call(i % 2 == 0, 10.0), range(40)))
    stats = store.llm_stats()
    assert stats["total_calls"] == 40
    assert stats["successful_calls"] == stats["failed_calls"] == 20
    assert stats["avg_latency_ms"] == 10.0
    sample = store.llm_stats(60)["retained_sample"]
    assert sample["total_calls"] == 40 and sample["successful_calls"] == 20


def test_llm_store_waits_for_a_contended_write_transaction(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    started = threading.Event()

    def record():
        started.set()
        store.record_llm_call(True, 25.0)

    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.connection() as blocker:
            blocker.execute("BEGIN IMMEDIATE")
            future = pool.submit(record)
            try:
                assert started.wait(5)
                # A direct store writer must tolerate contention beyond the
                # best-effort SDK capture sink's 100 ms budget.
                with pytest.raises(TimeoutError):
                    future.result(timeout=0.3)
            finally:
                blocker.rollback()
        future.result(timeout=5)

    assert store.llm_stats()["total_calls"] == 1
    assert store.llm_stats(60)["retained_sample"]["total_calls"] == 1


@pytest.mark.parametrize("duration", [-1, float("nan"), float("inf"), True])
def test_invalid_llm_measurement_does_not_change_counters(tmp_path, duration):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    with pytest.raises(ValueError):
        store.record_llm_call(True, duration)
    with pytest.raises(ValueError):
        store.record_llm_call("success", 1.0)
    assert store.llm_stats()["total_calls"] == 0


def test_persistence_and_full_window_statistics(tmp_path, clock):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    auth.add_user("u1", "alice", "alice@example.org", "irrelevant-hash")
    store = MonitorStore(auth)
    clock[0] = 120
    for index in range(20):
        store.record_request("get", "/items/{id}", 500 if index == 0 else 200, index + 1, "u1")
    clock[0] = 160
    restarted = MonitorStore(AuthStore(auth.path))
    stats = restarted.api_stats(60, "u1")
    assert stats["window_complete"] is True
    assert stats["source"] == "persisted_requests"
    assert stats["request_count"] == 20 and stats["errors"] == 1
    assert stats["avg_response_time_ms"] == 10.5
    assert stats["p95_response_time_ms"] == 19
    assert stats["requests_per_second"] == pytest.approx(20 / 60)
    assert auth.user("u1")["username"] == "alice"
    assert restarted.api_stats(60, "other")["request_count"] == 0
    assert restarted.api_stats(60, "other")["avg_response_time_ms"] is None


def test_startup_and_truncation_never_claim_complete_totals(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"), max_rows=2)
    store.record_request("GET", "/", 200, 1)
    startup = store.api_stats()
    assert not startup["window_complete"]
    assert startup["request_count"] is None and startup["requests_per_second"] is None
    assert startup["retained_sample"]["request_count"] == 1
    clock[0] = 120
    store.record_request("GET", "/", 400, 2)
    clock[0] = 121
    store.record_request("GET", "/", 200, 3)
    clock[0] = 122
    store.record_request("GET", "/", 500, 4)
    clock[0] = 160
    truncated = MonitorStore(AuthStore(store.auth_store.path), max_rows=2).api_stats(60)
    assert truncated["source"] == "retained_sample"
    assert truncated["request_count"] is None and truncated["errors"] is None
    assert truncated["avg_response_time_ms"] is None
    assert truncated["retained_sample"]["request_count"] == 2
    assert truncated["pruned_through"] == 120
    clock[0] = 183
    complete = store.api_stats(60)
    assert complete["window_complete"] and complete["request_count"] == 0


def test_retention_prunes_both_tables_without_resetting_watermark(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"), retention_seconds=30)
    clock[0] = 110
    store.record_request("GET", "/", 200, 1)
    store.append_log("INFO", "old")
    clock[0] = 150
    store.append_log("INFO", "current")
    assert [row["message"] for row in store.query_logs()[0]] == ["current"]
    stats = store.api_stats(60)
    assert not stats["window_complete"] and stats["request_count"] is None
    assert stats["retained_sample"]["request_count"] == 0
    assert stats["pruned_through"] == 110
    assert store.api_stats(10)["window_complete"]


def test_thread_instances_share_atomic_records(tmp_path):
    path = tmp_path / "auth.sqlite3"
    MonitorStore(AuthStore(path))

    def write(index):
        instance = MonitorStore(AuthStore(path))
        instance.record_request("POST", "/items", 201, index, "owner")
        instance.append_log("INFO", f"record-{index}", user_id="owner")

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(40)))
    store = MonitorStore(AuthStore(path))
    assert store.api_stats()["retained_sample"]["request_count"] == 40
    assert store.query_logs(user_id="owner")[1] == 40


def _write_from_process(path: str, index: int) -> None:
    store = MonitorStore(AuthStore(Path(path)))
    for offset in range(4):
        store.record_request("GET", "/process", 200, index + offset)
        store.append_log("INFO", f"process-{index}-{offset}")
        store.record_llm_call(True, 10)


def test_spawned_processes_share_persistent_records(tmp_path):
    path = tmp_path / "auth.sqlite3"
    MonitorStore(AuthStore(path))
    context = multiprocessing.get_context("spawn")
    processes = [context.Process(target=_write_from_process, args=(str(path), i)) for i in range(3)]
    for process in processes:
        process.start()
    for process in processes:
        process.join(20)
        if process.is_alive():
            process.terminate()
            process.join(5)
        assert process.exitcode == 0
    store = MonitorStore(AuthStore(path))
    assert store.api_stats()["retained_sample"]["request_count"] == 12
    assert store.query_logs()[1] == 12
    assert store.llm_stats(60)["retained_sample"]["total_calls"] == 12


def test_log_filtering_pagination_and_literal_search(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    for timestamp, level, message, owner, run in [
        (101, "INFO", "100% done", "alice", "run-a"),
        (102, "WARN", "100% pending", "alice", "run-a"),
        (103, "WARNING", "other", "bob", "run-b"),
        (104, "ERROR", "last", "alice", "run-a"),
    ]:
        clock[0] = timestamp
        store.append_log(level, message, owner, run)
    rows, total = store.query_logs(
        user_id="alice", run_id="run-a", start=101, end=104, limit=1, offset=1
    )
    assert total == 3 and rows[0]["message"] == "100% pending"
    assert store.query_logs(level="warn", user_id="alice")[1] == 1
    assert store.query_logs(search="100%")[1] == 2
    assert store.query_logs(search="%'")[1] == 0
    assert store.query_logs(user_id="' OR 1=1 --")[1] == 0
    assert store.query_logs(start=103, end=103)[1] == 1


def test_logs_are_redacted_before_persistence_and_bounded(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"), max_rows=2)
    secret = "actual-secret-value"
    store.append_log(
        "INFO",
        "password=hunter2 Authorization: Bearer bearer-token " + secret,
        context={"api_key": "provider-key", "nested": [{"text": secret, "password": "hunter2"}]},
        known_secrets=(secret,),
    )
    record = store.query_logs()[0][0]
    payload = json.dumps(record)
    assert "hunter2" not in payload and "provider-key" not in payload and secret not in payload
    assert "bearer-token" not in payload and "[REDACTED]" in payload
    with store.connection() as db:
        persisted = db.execute("SELECT message,context FROM api_monitor_logs").fetchone()
        assert "hunter2" not in " ".join(persisted)
    store.append_log("INFO", "x" * 50000, context={str(i): "汉" * 10000 for i in range(64)})
    rows, total = store.query_logs()
    assert total == 2 and len(rows[0]["message"]) == 4096
    assert len(json.dumps(rows[0]["context"]).encode()) < 16384
    cyclic = {}
    cyclic["self"] = cyclic
    store.append_log("INFO", "cycle", context=cyclic)
    assert store.query_logs()[1] == 2
    assert "[TRUNCATED]" in json.dumps(store.query_logs()[0][0]["context"])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"limit": 0},
        {"limit": 1001},
        {"offset": -1},
        {"start": float("nan")},
        {"end": -1},
        {"start": 2, "end": 1},
    ],
)
def test_log_query_rejects_invalid_ranges(tmp_path, kwargs):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    with pytest.raises(ValueError):
        store.query_logs(**kwargs)


def test_request_measurement_requires_real_finite_values(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    for status, duration in [(99, 1), (600, 1), (200, -1), (200, float("nan"))]:
        with pytest.raises(ValueError):
            store.record_request("GET", "/", status, duration)
    with pytest.raises(ValueError):
        store.api_stats(0)
    with pytest.raises(ValueError):
        store.append_log("unknown", "record")
    with pytest.raises(ValueError):
        MonitorStore(store.auth_store, max_rows=0)


def test_asgi_matches_route_template_and_uses_only_verified_scope_identity(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    app = FastAPI()
    app.state.monitor = SimpleNamespace(store=store)
    setup_logging_middleware(app)

    @app.get("/verified/{item_id}")
    async def verified(item_id: str, request: Request):
        request.scope.setdefault("state", {})["monitor_user_id"] = "verified-owner"
        return {"id": item_id}

    with TestClient(app) as client:
        client.get(
            "/verified/raw-secret-id?token=query-secret", headers={"Authorization": "Bearer fake"}
        )
        client.get("/not-found-secret?password=query-secret")
    with store.connection() as db:
        rows = [dict(row) for row in db.execute("SELECT * FROM api_monitor_requests ORDER BY id")]
    assert rows[0]["route"] == "/verified/{item_id}" and rows[0]["user_id"] == "verified-owner"
    assert rows[1]["route"] == "[unmatched]" and rows[1]["user_id"] is None
    assert "secret" not in json.dumps(rows) and "fake" not in json.dumps(rows)


def test_asgi_records_final_outer_rejection(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    app = FastAPI()
    app.state.monitor = SimpleNamespace(store=store)
    app.add_middleware(AuthBoundaryMiddleware)
    setup_logging_middleware(app)
    with TestClient(app) as client:
        response = client.post("/api/v1/auth/register", content=b"x" * 20000)
    assert response.status_code == 413
    with store.connection() as db:
        row = db.execute("SELECT * FROM api_monitor_requests").fetchone()
        assert row["status_code"] == 413 and row["route"] == "[unmatched]"


def test_asgi_records_unhandled_exception_as_final_server_error(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    app = FastAPI()
    app.state.monitor = SimpleNamespace(store=store)
    setup_logging_middleware(app)

    @app.get("/failure")
    async def failure():
        raise RuntimeError("business failure")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/failure")
    assert response.status_code == 500
    with store.connection() as db:
        assert db.execute("SELECT status_code FROM api_monitor_requests").fetchone()[0] == 500


def test_asgi_latency_excludes_work_after_completed_response(monkeypatch):
    clock = [10.0]
    monkeypatch.setattr(logging_module, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    records = []
    monitor = SimpleNamespace(
        store=SimpleNamespace(record_request=lambda *args: records.append(args))
    )
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "app": SimpleNamespace(state=SimpleNamespace(monitor=monitor)),
    }

    async def downstream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200})
        clock[0] = 11.0
        await send({"type": "http.response.body", "body": b"ok"})
        # ASGI background tasks execute after the client has received the body.
        clock[0] = 99.0

    async def send(message):
        pass

    asyncio.run(LoggingMiddleware(downstream)(scope, None, send))
    assert records[0][3] == 1000


def test_asgi_write_failure_preserves_response_and_original_exception():
    class BrokenStore:
        def record_request(self, *args):
            raise RuntimeError("database unavailable")

    app_state = SimpleNamespace(state=SimpleNamespace(monitor=SimpleNamespace(store=BrokenStore())))
    scope = {"type": "http", "method": "GET", "path": "/sensitive", "app": app_state}
    sent = []

    async def receive():
        return {"type": "http.request", "body": b""}

    async def send(message):
        sent.append(message)

    async def response_app(scope, receive, send):
        await JSONResponse({"ok": True}, status_code=201)(scope, receive, send)

    asyncio.run(LoggingMiddleware(response_app)(scope, receive, send))
    assert sent[0]["status"] == 201
    original = RuntimeError("original business failure")

    async def failing_app(scope, receive, send):
        raise original

    with pytest.raises(RuntimeError) as caught:
        asyncio.run(LoggingMiddleware(failing_app)(scope, receive, send))
    assert caught.value is original


def test_non_http_scope_is_not_monitored():
    seen = []

    async def downstream(scope, receive, send):
        seen.append(scope["type"])

    asyncio.run(LoggingMiddleware(downstream)({"type": "websocket"}, None, None))
    assert seen == ["websocket"]


def test_disconnected_request_without_response_does_not_invent_status(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    app_state = SimpleNamespace(state=SimpleNamespace(monitor=SimpleNamespace(store=store)))

    async def downstream(scope, receive, send):
        assert (await receive())["type"] == "http.disconnect"

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        raise AssertionError("Disconnected request must not send a response")

    scope = {"type": "http", "method": "GET", "path": "/", "app": app_state}
    asyncio.run(LoggingMiddleware(downstream)(scope, receive, send))
    assert store.api_stats()["retained_sample"]["request_count"] == 0


def test_failed_capture_remembers_gap_until_database_recovers(tmp_path, clock, monkeypatch):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    clock[0] = 120
    connection = store.connection

    def unavailable():
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(store, "connection", unavailable)
    app_state = SimpleNamespace(state=SimpleNamespace(monitor=SimpleNamespace(store=store)))
    scope = {"type": "http", "method": "GET", "path": "/", "app": app_state}
    sent = []

    async def downstream(scope, receive, send):
        await JSONResponse({"ok": True})(scope, receive, send)

    async def send(message):
        sent.append(message)

    asyncio.run(LoggingMiddleware(downstream)(scope, None, send))
    assert sent[0]["status"] == 200
    monkeypatch.setattr(store, "connection", connection)
    clock[0] = 160
    recovered = store.api_stats(60)
    assert not recovered["window_complete"] and recovered["request_count"] is None
    assert recovered["source"] == "retained_sample" and recovered["capture_gap_through"] == 120
    restarted = MonitorStore(AuthStore(store.auth_store.path))
    assert restarted.api_stats(60)["capture_gap_through"] == 120
    clock[0] = 181
    assert restarted.api_stats(60)["window_complete"]


def test_capture_gap_is_shared_immediately_when_database_is_writable(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    other = MonitorStore(AuthStore(store.auth_store.path))
    clock[0] = 125
    store.mark_capture_gap()
    clock[0] = 160
    assert other.api_stats(60)["capture_gap_through"] == 125
    assert not other.api_stats(60)["window_complete"]


def test_log_export_uses_one_snapshot_and_owner_filters(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    with store.connection() as db:
        db.executemany(
            "INSERT INTO api_monitor_logs(timestamp,level,message,user_id,run_id,context) VALUES (?,?,?,?,?,?)",
            [(100, "INFO", f"line-{i}", "alice", "run-a", "{}") for i in range(1005)],
        )
    store.append_log("INFO", "other-owner", "bob", "run-b")
    attempted = threading.Event()
    writer_errors = []

    def writer():
        attempted.set()
        try:
            store.append_log("INFO", "concurrent-new", "alice", "run-a")
        except Exception as error:
            writer_errors.append(error)

    thread = threading.Thread(target=writer)

    class ConcurrentStream(io.BytesIO):
        started = False

        def write(self, data):
            if not self.started:
                self.started = True
                thread.start()
                assert attempted.wait(5)
            return super().write(data)

    stream = ConcurrentStream()
    result = store.export_logs(stream, user_id="alice", run_id="run-a")
    thread.join(20)
    assert not thread.is_alive() and not writer_errors
    lines = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert result == {"total": 1005, "exported": 1005, "truncated": False}
    assert len(lines) == 1005 and len({line["id"] for line in lines}) == 1005
    assert (
        "concurrent-new" not in stream.getvalue().decode()
        and "other-owner" not in stream.getvalue().decode()
    )
    assert store.query_logs(user_id="alice")[1] == 1006


def test_log_export_byte_cap_preserves_whole_unicode_lines(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    store.append_log("ERROR", "中文 password=secret", "alice", "run-a")
    store.append_log("INFO", "skip", "bob", "run-b")
    stream = io.BytesIO()
    complete = store.export_logs(stream, level="ERROR", user_id="alice", run_id="run-a")
    raw = stream.getvalue()
    assert complete == {"total": 1, "exported": 1, "truncated": False}
    assert "中文" in raw.decode() and "secret" not in raw.decode()
    bounded = io.BytesIO()
    partial = store.export_logs(bounded, level="ERROR", max_bytes=len(raw) - 1)
    assert bounded.getvalue() == b""
    assert partial == {"total": 1, "exported": 0, "truncated": True}
    with pytest.raises(ValueError):
        store.export_logs(bounded, max_bytes=0)


def test_short_secret_does_not_corrupt_ownership_selectors(tmp_path):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    owner = "aaaaaaaa-1111-2222-3333-444444444444"
    run = "bbbbbbbb-aaaa-2222-3333-444444444444"
    store.append_log("INFO", "a", owner, run, known_secrets=("a",))
    rows, total = store.query_logs(user_id=owner, run_id=run)
    assert total == 1 and rows[0]["message"] == "[REDACTED]"
    assert rows[0]["user_id"] == owner and rows[0]["run_id"] == run


def test_endpoint_statistics_group_methods_and_preserve_incomplete_sample(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    clock[0] = 120
    store.record_request("GET", "/items/{item_id}", 200, 10)
    store.record_request("POST", "/items/{item_id}", 201, 30)
    store.record_request("GET", "/items/{item_id}", 500, 40)
    clock[0] = 160
    complete = store.api_stats(60)
    assert complete["error_rate"] == pytest.approx(1 / 3)
    groups = {item["method"]: item for item in complete["endpoints"]}
    assert groups["GET"]["count"] == 2 and groups["GET"]["errors"] == 1
    assert groups["GET"]["error_rate"] == 0.5
    assert groups["GET"]["avg_response_time_ms"] == 25
    assert groups["GET"]["p95_response_time_ms"] == 40
    assert groups["POST"]["count"] == 1 and groups["POST"]["error_rate"] == 0
    assert all(item["route"] == "/items/{item_id}" for item in complete["endpoints"])
    store.mark_capture_gap(125)
    incomplete = store.api_stats(60)
    assert incomplete["error_rate"] is None
    for item in incomplete["endpoints"]:
        assert not item["window_complete"] and item["count"] is None and item["error_rate"] is None
        assert item["avg_response_time_ms"] is None and item["retained_sample"]["count"] > 0


def test_llm_window_uses_completion_time_and_inclusive_boundaries(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    for when, success, duration in [
        (109, True, 999),
        (110, True, 100),
        (135, False, 300),
        (170, True, 200),
        (171, False, 999),
    ]:
        clock[0] = when
        store.record_llm_call(success, duration)
    clock[0] = 170
    stats = MonitorStore(AuthStore(store.auth_store.path)).llm_stats(60)
    assert stats["window_complete"] is True
    assert stats["window_start"] == 110 and stats["window_end"] == 170
    assert stats["window_seconds"] == 60
    assert stats["total_calls"] == 3
    assert stats["successful_calls"] == 2 and stats["failed_calls"] == 1
    assert stats["success_rate"] == pytest.approx(2 / 3)
    assert stats["avg_latency_ms"] == 200
    assert store.llm_stats()["total_calls"] == 5


def test_llm_window_empty_and_startup_do_not_invent_history(tmp_path, clock):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    startup = store.llm_stats(60)
    assert not startup["window_complete"] and startup["total_calls"] is None
    assert startup["retained_sample"]["total_calls"] == 0
    clock[0] = 160
    empty = store.llm_stats(60)
    assert empty["window_complete"] and empty["total_calls"] == 0
    assert empty["success_rate"] is None and empty["avg_latency_ms"] is None


@pytest.mark.parametrize("limits", [{"max_rows": 2}, {"retention_seconds": 30}])
def test_llm_window_pruning_survives_restart_without_losing_cumulative(tmp_path, clock, limits):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"), **limits)
    for when in (110, 120, 121):
        clock[0] = when
        store.record_llm_call(True, 100)
    clock[0] = 160
    restarted = MonitorStore(AuthStore(store.auth_store.path), **limits)
    stats = restarted.llm_stats(60)
    assert not stats["window_complete"] and stats["total_calls"] is None
    assert stats["pruned_through"] >= 110
    assert stats["retained_sample"]["total_calls"] == (2 if "max_rows" in limits else 0)
    assert restarted.llm_stats()["total_calls"] == 3
    clock[0] = 182
    assert restarted.llm_stats(60)["window_complete"]


def test_llm_window_upgrade_preserves_cumulative_without_backfill(tmp_path, clock):
    auth = AuthStore(tmp_path / "auth.sqlite3")
    with auth.connection() as db:
        db.execute("CREATE TABLE api_monitor_meta(key TEXT PRIMARY KEY, value REAL NOT NULL)")
        db.executemany(
            "INSERT INTO api_monitor_meta VALUES (?,?)",
            [
                ("llm_started_at", 1),
                ("llm_total_calls", 2),
                ("llm_successful_calls", 1),
                ("llm_failed_calls", 1),
                ("llm_duration_ms", 400),
            ],
        )
    store = MonitorStore(auth)
    assert store.llm_stats()["total_calls"] == 2
    assert not store.llm_stats(60)["window_complete"]
    clock[0] = 160
    assert store.llm_stats(60)["total_calls"] == 0


@pytest.mark.parametrize("window", [0, -1, 86401, True, 1.5, "60"])
def test_llm_window_rejects_invalid_window(tmp_path, window):
    store = MonitorStore(AuthStore(tmp_path / "auth.sqlite3"))
    with pytest.raises(ValueError):
        store.llm_stats(window)
