"""Real cursor execution measurements without SQL or credential retention."""

import gc
import json
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import OperationalError

import api.monitoring.database_metrics as metrics_module
from api.monitoring.database_metrics import DatabaseQueryMetrics


@pytest.fixture
def clock(monkeypatch):
    value = SimpleNamespace(wall=100.0, monotonic=0.0)
    monkeypatch.setattr(
        metrics_module,
        "time",
        SimpleNamespace(time=lambda: value.wall, perf_counter=lambda: value.monotonic),
    )
    return value


@pytest.fixture
def engine():
    value = create_engine("sqlite:///:memory:")
    yield value
    value.dispose()


def test_real_success_failure_counts_and_latency(engine, clock):
    metrics = DatabaseQueryMetrics(engine)
    duration = [0.0]

    def driver_time(conn, cursor, statement, parameters, context, executemany):
        clock.monotonic += duration[0]

    event.listen(engine, "before_cursor_execute", driver_time)
    clock.wall, clock.monotonic = 120.0, 20.0
    with engine.connect() as conn:
        for elapsed in (0.001, 0.002, 0.003):
            duration[0] = elapsed
            assert conn.execute(text("SELECT 42")).scalar() == 42
        duration[0] = 0.004
        with pytest.raises(OperationalError, match="no such table"):
            conn.execute(text("SELECT * FROM nonexistent_table"))
    clock.wall, clock.monotonic = 160.0, 60.0
    stats = metrics.stats(60)
    assert stats["status"] == "ok"
    assert stats["source"] == "captured_business_queries"
    assert stats["scope"] == "bound_business_engine_current_process"
    assert stats["window_complete"]
    assert stats["query_count"] == 4 and stats["successes"] == 3 and stats["errors"] == 1
    assert stats["error_rate"] == 0.25
    assert stats["avg_latency_ms"] == pytest.approx(2.5)
    assert stats["p95_latency_ms"] == pytest.approx(4.0)
    assert stats["queries_per_second"] == pytest.approx(4 / 60)
    metrics.close()
    event.remove(engine, "before_cursor_execute", driver_time)


def test_initial_window_reports_only_sample(engine, clock):
    metrics = DatabaseQueryMetrics(engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    stats = metrics.stats()
    assert not stats["window_complete"]
    assert stats["source"] == "retained_sample"
    for name in metrics_module._METRIC_NAMES:
        assert stats[name] is None
    assert stats["retained_sample"]["query_count"] == 1
    metrics.close()


def test_row_limit_incomplete_until_pruned_query_leaves_window(engine, clock):
    metrics = DatabaseQueryMetrics(engine, max_rows=2)
    with engine.connect() as conn:
        for timestamp in (110, 120, 130):
            clock.wall, clock.monotonic = timestamp, timestamp - 100
            conn.execute(text("SELECT 1"))
    clock.wall, clock.monotonic = 160.0, 60.0
    truncated = metrics.stats(60)
    assert not truncated["window_complete"]
    assert truncated["query_count"] is None
    assert truncated["retained_sample"]["query_count"] == 2
    assert truncated["pruned_through"] == 110
    assert len(metrics._records) == 2
    clock.wall, clock.monotonic = 171.0, 71.0
    assert metrics.stats(60)["window_complete"]
    metrics.close()


def test_retention_and_empty_window(engine, clock):
    metrics = DatabaseQueryMetrics(engine, retention_seconds=30)
    clock.wall, clock.monotonic = 110.0, 10.0
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    clock.wall, clock.monotonic = 150.0, 50.0
    stats = metrics.stats(60)
    assert not stats["window_complete"]
    assert stats["retained_sample"]["query_count"] == 0
    assert stats["pruned_through"] == 110
    assert not metrics._records
    complete = metrics.stats(10)
    assert complete["window_complete"] and complete["query_count"] == 0
    assert complete["successes"] == 0 and complete["errors"] == 0
    assert complete["error_rate"] is None and complete["avg_latency_ms"] is None
    assert complete["p95_latency_ms"] is None
    metrics.close()


def test_window_uses_monotonic_clock_when_wall_clock_moves(engine, clock):
    metrics = DatabaseQueryMetrics(engine)
    clock.wall, clock.monotonic = 20.0, 10.0
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    clock.wall, clock.monotonic = 30.0, 60.0
    stats = metrics.stats(60)
    assert stats["window_complete"] and stats["query_count"] == 1
    metrics.close()


def test_threaded_queries_are_atomic_and_engine_scoped(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'business.sqlite3'}")
    other = create_engine("sqlite:///:memory:")
    metrics = DatabaseQueryMetrics(engine)
    independent = DatabaseQueryMetrics(other)

    def query(index):
        with engine.connect() as conn:
            assert conn.execute(text("SELECT :value"), {"value": index}).scalar() == index

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(query, range(80)))
    assert metrics.stats()["retained_sample"]["query_count"] == 80
    assert independent.stats()["retained_sample"]["query_count"] == 0
    with other.connect() as conn:
        conn.execute(text("SELECT 1"))
    assert independent.stats()["retained_sample"]["query_count"] == 1
    metrics.close()
    independent.close()
    engine.dispose()
    other.dispose()


def test_independent_collectors_on_same_engine_and_close(engine):
    first = DatabaseQueryMetrics(engine)
    second = DatabaseQueryMetrics(engine)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    first.close()
    first.close()
    assert first not in first._bridge._collectors
    assert second in first._bridge._collectors
    with engine.connect() as conn:
        conn.execute(text("SELECT 2"))
    stopped = first.stats()
    assert stopped["status"] == "not_collecting" and not stopped["collection_active"]
    assert not stopped["window_complete"] and stopped["query_count"] is None
    assert stopped["retained_sample"]["query_count"] == 1
    assert second.stats()["retained_sample"]["query_count"] == 2
    second.close()


def test_repeated_collectors_reuse_bridge_without_retention_or_duplicate_counts(engine):
    first = DatabaseQueryMetrics(engine)
    bridge = first._bridge
    listener_counts = (
        len(engine.dispatch.before_cursor_execute),
        len(engine.dispatch.after_cursor_execute),
        len(engine.dialect.dispatch.handle_error),
    )
    reference = weakref.ref(first)
    first.close()
    del first
    gc.collect()
    assert reference() is None
    assert not bridge._collectors
    for _ in range(20):
        current = DatabaseQueryMetrics(engine)
        assert current._bridge is bridge
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        assert current.stats()["retained_sample"]["query_count"] == 1
        current.close()
    assert not bridge._collectors
    assert listener_counts == (
        len(engine.dispatch.before_cursor_execute),
        len(engine.dispatch.after_cursor_execute),
        len(engine.dialect.dispatch.handle_error),
    )


def test_bridge_does_not_keep_disposed_engine_alive():
    engine = create_engine("sqlite:///:memory:")
    collector = DatabaseQueryMetrics(engine)
    engine_reference = weakref.ref(engine)
    bridge_reference = weakref.ref(collector._bridge)
    collector.close()
    engine.dispose()
    del collector
    del engine
    gc.collect()
    assert engine_reference() is None
    # The weak-key removal during the first collection releases the bridge's
    # last registry reference; its stored bound callbacks form a small cycle.
    gc.collect()
    assert bridge_reference() is None


@pytest.mark.parametrize("hook", ["_start", "_record"])
def test_shutdown_during_listener_does_not_change_original_query(tmp_path, monkeypatch, hook):
    engine = create_engine(f"sqlite:///{tmp_path / 'shutdown.sqlite3'}")
    metrics = DatabaseQueryMetrics(engine)
    entered, resume = threading.Event(), threading.Event()
    original_hook = getattr(metrics, hook)

    def blocked_hook(*args):
        entered.set()
        assert resume.wait(5), "Shutdown test did not release the running callback"
        original_hook(*args)

    monkeypatch.setattr(metrics, hook, blocked_hook)

    def query():
        with engine.connect() as conn:
            return conn.execute(text("SELECT 7")).scalar()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(query)
            try:
                assert entered.wait(5), "Query did not reach the monitoring callback"
                metrics.close()
            finally:
                resume.set()
            assert future.result(timeout=5) == 7
            assert metrics.stats()["retained_sample"]["query_count"] == 0
    finally:
        resume.set()
        metrics.close()
        engine.dispose()


def test_no_sql_parameters_or_exception_text_in_retained_data(engine):
    metrics = DatabaseQueryMetrics(engine)
    with engine.connect() as conn:
        conn.execute(
            text("SELECT :password /* private-query-secret */"), {"password": "key-secret"}
        )
        with pytest.raises(OperationalError):
            conn.execute(text("SELECT * FROM private_error_secret"))
    serialized = json.dumps(metrics.stats()) + repr(metrics._records)
    for secret in ("private-query-secret", "key-secret", "private_error_secret", "SELECT"):
        assert secret not in serialized
    assert len(metrics._records) == 2
    metrics.close()


def test_failed_recording_preserves_result_and_original_error(engine, clock, monkeypatch):
    metrics = DatabaseQueryMetrics(engine)

    def unavailable(*args):
        raise RuntimeError("sensitive monitor error")

    monkeypatch.setattr(metrics, "_record", unavailable)
    clock.wall, clock.monotonic = 120.0, 20.0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 7")).scalar() == 7
        with pytest.raises(OperationalError, match="no such table: original_failure"):
            conn.execute(text("SELECT * FROM original_failure"))
    clock.wall, clock.monotonic = 160.0, 60.0
    stats = metrics.stats()
    assert not stats["window_complete"] and stats["query_count"] is None
    assert stats["capture_gap_through"] == 120.0
    assert stats["retained_sample"]["query_count"] == 0
    assert "sensitive" not in json.dumps(stats)
    metrics.close()


def test_failed_start_hook_does_not_change_business_execution(engine, clock, monkeypatch):
    metrics = DatabaseQueryMetrics(engine)

    def cannot_start(context):
        raise RuntimeError("sensitive start error")

    monkeypatch.setattr(metrics, "_start", cannot_start)
    clock.wall, clock.monotonic = 120.0, 20.0
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 9")).scalar() == 9
    clock.wall, clock.monotonic = 160.0, 60.0
    stats = metrics.stats()
    assert not stats["window_complete"]
    assert stats["retained_sample"]["query_count"] == 0
    metrics.close()


def test_connection_error_without_execution_context_is_not_a_query(engine, clock):
    metrics = DatabaseQueryMetrics(engine)
    metrics._handle_error(SimpleNamespace(execution_context=None))
    clock.wall, clock.monotonic = 160.0, 60.0
    stats = metrics.stats()
    assert stats["window_complete"] and stats["query_count"] == 0
    assert stats["capture_gap_through"] is None
    metrics.close()


def test_missing_execution_start_marks_gap_without_fake_query(engine, clock):
    metrics = DatabaseQueryMetrics(engine)
    clock.wall, clock.monotonic = 120.0, 20.0
    metrics._handle_error(SimpleNamespace(execution_context=SimpleNamespace()))
    clock.wall, clock.monotonic = 160.0, 60.0
    assert not metrics.stats()["window_complete"]
    assert metrics.stats()["retained_sample"]["query_count"] == 0
    clock.wall, clock.monotonic = 181.0, 81.0
    assert metrics.stats()["window_complete"]
    metrics.close()


def test_executemany_is_one_cursor_execution(engine):
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE values_table (number INTEGER)"))
    metrics = DatabaseQueryMetrics(engine)
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO values_table VALUES (:number)"),
            [{"number": 1}, {"number": 2}, {"number": 3}],
        )
    assert metrics.stats()["retained_sample"]["query_count"] == 1
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM values_table")).scalar() == 3
    metrics.close()


def test_hook_clock_failure_cannot_fail_query_or_claim_coverage(engine, clock, monkeypatch):
    metrics = DatabaseQueryMetrics(engine)

    def failed_clock():
        raise OSError("clock failure secret")

    monkeypatch.setattr(metrics_module.time, "perf_counter", failed_clock)
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 13")).scalar() == 13
        with pytest.raises(OperationalError, match="no such table: original_error"):
            conn.execute(text("SELECT * FROM original_error"))
    monkeypatch.setattr(metrics_module.time, "perf_counter", lambda: clock.monotonic)
    clock.wall, clock.monotonic = 160.0, 60.0
    assert not metrics.stats()["window_complete"]
    assert metrics.stats()["query_count"] is None
    assert metrics.stats()["retained_sample"]["query_count"] == 0
    metrics.close()


def test_collection_coverage_begins_after_listener_registration(engine, clock, monkeypatch):
    original_listen = metrics_module.event.listen

    def delayed_listen(*args, **kwargs):
        original_listen(*args, **kwargs)
        clock.wall += 1
        clock.monotonic += 1

    monkeypatch.setattr(metrics_module.event, "listen", delayed_listen)
    metrics = DatabaseQueryMetrics(engine)
    clock.wall, clock.monotonic = 160.0, 60.0
    assert not metrics.stats(60)["window_complete"]
    clock.wall, clock.monotonic = 163.0, 63.0
    assert metrics.stats(60)["window_complete"]
    metrics.close()


@pytest.mark.parametrize("kwargs", [{"retention_seconds": 0}, {"max_rows": 0}])
def test_invalid_limits(engine, kwargs):
    with pytest.raises(ValueError):
        DatabaseQueryMetrics(engine, **kwargs)


def test_invalid_window(engine):
    metrics = DatabaseQueryMetrics(engine)
    with pytest.raises(ValueError):
        metrics.stats(0)
    metrics.close()


def test_sqlite_calls_preserve_transactions_and_isolate_capture_failure(
    tmp_path, clock, monkeypatch
):
    import sqlite3

    from api.auth.store import AuthStore
    from api.monitoring.database_metrics import SQLiteQueryMetrics

    store = AuthStore(tmp_path / "auth.db")
    metrics = SQLiteQueryMetrics(max_rows=20)
    store.attach_query_metrics(metrics)
    with store.connection() as db:
        db.executescript(
            'CREATE TABLE sample (value TEXT UNIQUE); INSERT INTO sample VALUES ("a");'
        )
        cursor = db.cursor()
        assert cursor.execute("SELECT value FROM sample").fetchone()[0] == "a"
        cursor.executemany("INSERT INTO sample VALUES (?)", [("b",), ("c",)])
    with pytest.raises(sqlite3.IntegrityError):
        with store.connection() as db:
            db.execute("INSERT INTO sample VALUES (?)", ("rollback",))
            db.execute("INSERT INTO sample VALUES (?)", ("a",))
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM sample").fetchone()[0] == 3
    stats = metrics.stats(60)
    assert stats["retained_sample"]["errors"] == 1
    assert stats["retained_sample"]["query_count"] == 9
    assert stats["query_count"] is None and not stats["window_complete"]
    clock.wall, clock.monotonic = 160, 60
    assert metrics.stats(60)["window_complete"]
    with monkeypatch.context() as patcher:
        patcher.setattr(metrics, "_record", lambda *args: (_ for _ in ()).throw(RuntimeError()))
        with store.connection() as db:
            assert db.execute("SELECT 7").fetchone()[0] == 7
            with pytest.raises(sqlite3.OperationalError):
                db.execute("SELECT * FROM nonexistent")
    assert not metrics.stats(60)["window_complete"]
    metrics.close()
    store.detach_query_metrics(metrics)
    before = metrics.stats()["retained_sample"]["query_count"]
    with store.connection() as db:
        db.execute("SELECT 1")
    assert metrics.stats()["retained_sample"]["query_count"] == before
    replacement = SQLiteQueryMetrics()
    store.attach_query_metrics(replacement)
    with store.connection() as db:
        db.execute("SELECT 2")
    assert replacement.stats()["retained_sample"]["query_count"] == 2
    assert metrics.stats()["retained_sample"]["query_count"] == before


def test_monitor_deduplicates_shared_engines(tmp_path):
    from api.auth.store import AuthStore
    from api.monitoring.config import MonitorSettings
    from api.monitoring.service import MonitorService

    store = AuthStore(tmp_path / "auth.db")
    engine = create_engine("sqlite://")
    settings = MonitorSettings(_env_file=None)
    auth = SimpleNamespace(store=store)
    files = SimpleNamespace(store=SimpleNamespace(auth_store=store))
    monitor = MonitorService(
        auth,
        files,
        SimpleNamespace(engine=engine),
        settings,
        task_engine=engine,
        database_engines={"experiment": engine},
    )
    with engine.connect() as db:
        db.execute(text("SELECT 1"))
    sources = monitor.database_sources()
    assert len(sources) == 2
    assert sources[0]["roles"] == ["evaluation", "async_task", "experiment"]
    assert sources[0]["retained_sample"]["query_count"] == 1
    monitor.close()
    assert all(not source["collection_active"] for source in monitor.database_sources())
    engine.dispose()
