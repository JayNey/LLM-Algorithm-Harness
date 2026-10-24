"""Bounded execution metrics for bound database sources in the current process.

These records are not durable or shared between workers. SQL text, parameters,
connection URLs and exception messages are never copied into the samples. The
latency covers cursor execution, excluding connection acquisition and fetching.
"""

import math
import sqlite3
import threading
import time
import uuid
import weakref
from collections import deque
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import event
from sqlalchemy.engine import Engine

_METRIC_NAMES = (
    "query_count",
    "successes",
    "errors",
    "error_rate",
    "avg_latency_ms",
    "p95_latency_ms",
    "queries_per_second",
)


@dataclass(frozen=True, slots=True)
class _Sample:
    timestamp: float
    monotonic: float
    duration_ms: float
    succeeded: bool


class _EngineBridge:
    """Stable engine callbacks with no strong engine or collector references.

    SQLAlchemy event collections cannot be changed while they are dispatching.
    Install this bridge before serving requests and retain it for the engine's
    lifetime. Closing or opening a collector only changes this weak registry.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._collectors: weakref.WeakSet[DatabaseQueryMetrics] = weakref.WeakSet()
        self.capture_unavailable = False
        self._before_listener = self._before_cursor_execute
        self._after_listener = self._after_cursor_execute
        self._error_listener = self._handle_error

    def listeners(self) -> tuple[tuple[str, Any], ...]:
        return (
            ("before_cursor_execute", self._before_listener),
            ("after_cursor_execute", self._after_listener),
            ("handle_error", self._error_listener),
        )

    def add(self, collector: "DatabaseQueryMetrics") -> None:
        with self._lock:
            self._collectors.add(collector)

    def discard(self, collector: "DatabaseQueryMetrics") -> None:
        with self._lock:
            self._collectors.discard(collector)

    def _dispatch(self, method: str, args: tuple[Any, ...]) -> None:
        try:
            with self._lock:
                collectors = tuple(self._collectors)
        except Exception:
            # A failed registry snapshot cannot alter the business operation
            # or leave its collectors claiming complete collection coverage.
            self.capture_unavailable = True
            return
        for collector in collectors:
            try:
                getattr(collector, method)(*args)
            except Exception:
                collector._safe_gap()

    def _before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        self._dispatch(
            "_before_cursor_execute", (conn, cursor, statement, parameters, context, executemany)
        )

    def _after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        self._dispatch(
            "_after_cursor_execute", (conn, cursor, statement, parameters, context, executemany)
        )

    def _handle_error(self, exception_context: Any) -> None:
        self._dispatch("_handle_error", (exception_context,))


_BRIDGES: weakref.WeakKeyDictionary[Engine, _EngineBridge] = weakref.WeakKeyDictionary()
_BRIDGES_LOCK = threading.Lock()


def _bridge_for_engine(engine: Engine) -> _EngineBridge:
    # First registration must happen during startup, before the engine serves
    # concurrent queries. Reopening collectors never mutates event deques.
    with _BRIDGES_LOCK:
        existing = _BRIDGES.get(engine)
        if existing is not None:
            return existing
        bridge = _EngineBridge()
        registered = []
        try:
            for name, callback in bridge.listeners():
                event.listen(engine, name, callback)
                registered.append((name, callback))
        except Exception:
            for name, callback in registered:
                event.remove(engine, name, callback)
            raise
        _BRIDGES[engine] = bridge
        return bridge


class DatabaseQueryMetrics:
    def __init__(
        self, engine: Engine | None, retention_seconds: int = 604800, max_rows: int = 10000
    ):
        if retention_seconds < 1 or max_rows < 1:
            raise ValueError("Query metrics retention and row limit must be positive")
        self.engine = engine
        self.retention_seconds = retention_seconds
        self.max_rows = max_rows
        self._lock = threading.Lock()
        self._records: deque[_Sample] = deque()
        self._closed = False
        self._capture_unavailable = False
        self.started_at = time.time()
        self._started_monotonic = time.perf_counter()
        self._pruned_monotonic: float | None = None
        self._gap_monotonic: float | None = None
        self._pruned_through: float | None = None
        self._capture_gap_through: float | None = None
        # Separate collectors can observe the same engine without overwriting
        # each other's execution start values on the transient context.
        self._context_key = "_llm_query_monitor_" + uuid.uuid4().hex
        self._bridge = _bridge_for_engine(engine) if engine is not None else _EngineBridge()
        self._bridge.add(self)
        with self._lock:
            # Only promise collection coverage once all listeners are bound.
            # Any queries concurrent with initial registration remain samples.
            self.started_at = time.time()
            self._started_monotonic = time.perf_counter()

    def _mark_gap(self) -> None:
        with self._lock:
            if self._closed:
                return
            wall, monotonic = time.time(), time.perf_counter()
            if not math.isfinite(wall) or not math.isfinite(monotonic):
                self._capture_unavailable = True
                return
            self._gap_monotonic = max(self._gap_monotonic or monotonic, monotonic)
            self._capture_gap_through = wall

    def _safe_gap(self) -> None:
        try:
            self._mark_gap()
        except Exception:
            # Even a broken clock or the gap recorder must not change the
            # original response. Without a trustworthy watermark, no future
            # statistics can claim a complete collection window.
            self._capture_unavailable = True

    def _start(self, context: Any) -> None:
        with self._lock:
            if self._closed:
                return
            started = time.perf_counter()
            if not math.isfinite(started):
                raise ValueError("Invalid query start clock")
            setattr(context, self._context_key, started)

    def _before_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        try:
            self._start(context)
        except Exception:
            self._safe_gap()

    def _finish(self, context: Any, succeeded: bool) -> None:
        started = getattr(context, self._context_key, None)
        if started is None:
            self._safe_gap()
            return
        delattr(context, self._context_key)
        elapsed_ms = (time.perf_counter() - started) * 1000
        self._record(elapsed_ms, succeeded)

    def _after_cursor_execute(
        self,
        conn: Any,
        cursor: Any,
        statement: Any,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        try:
            self._finish(context, True)
        except Exception:
            self._safe_gap()

    def _handle_error(self, exception_context: Any) -> None:
        try:
            context = exception_context.execution_context
            # A pool/connection error before cursor execution is not a query.
            if context is not None:
                self._finish(context, False)
        except Exception:
            self._safe_gap()
        # Always return None: SQLAlchemy must preserve the original exception.

    def _prune(self, monotonic: float) -> None:
        cutoff = monotonic - self.retention_seconds
        while self._records and (
            self._records[0].monotonic < cutoff or len(self._records) > self.max_rows
        ):
            sample = self._records.popleft()
            self._pruned_monotonic = max(
                self._pruned_monotonic or sample.monotonic, sample.monotonic
            )
            self._pruned_through = sample.timestamp

    def _record(self, duration_ms: float, succeeded: bool) -> None:
        if not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("Invalid query duration")
        with self._lock:
            if self._closed:
                return
            wall, monotonic = time.time(), time.perf_counter()
            if not math.isfinite(wall) or not math.isfinite(monotonic):
                raise ValueError("Invalid query completion clock")
            self._records.append(_Sample(wall, monotonic, duration_ms, succeeded))
            self._prune(monotonic)

    @staticmethod
    def _summary(records: list[_Sample], window_seconds: int) -> dict[str, Any]:
        durations = sorted(sample.duration_ms for sample in records)
        count = len(records)
        successes = sum(sample.succeeded for sample in records)
        errors = count - successes
        return {
            "query_count": count,
            "successes": successes,
            "errors": errors,
            "error_rate": errors / count if count else None,
            "avg_latency_ms": sum(durations) / count if count else None,
            "p95_latency_ms": durations[math.ceil(0.95 * count) - 1] if count else None,
            "queries_per_second": count / window_seconds,
        }

    def stats(self, window_seconds: int = 60) -> dict[str, Any]:
        if window_seconds < 1:
            raise ValueError("Query statistics window must be positive")
        with self._lock:
            now = time.perf_counter()
            self._prune(now)
            cutoff = now - window_seconds
            records = [sample for sample in self._records if cutoff <= sample.monotonic <= now]
            complete = (
                not self._closed
                and not self._capture_unavailable
                and not self._bridge.capture_unavailable
                and self._started_monotonic <= cutoff
                and window_seconds <= self.retention_seconds
                and (self._pruned_monotonic is None or self._pruned_monotonic < cutoff)
                and (self._gap_monotonic is None or self._gap_monotonic < cutoff)
            )
            sample = self._summary(records, window_seconds)
            return {
                **(sample if complete else dict.fromkeys(_METRIC_NAMES)),
                "status": "not_collecting" if self._closed else "ok",
                "source": "captured_business_queries" if complete else "retained_sample",
                "scope": "bound_business_engine_current_process",
                "latency_scope": "cursor_execution_excludes_pool_wait_and_fetch",
                "window_complete": complete,
                "collection_active": not self._closed,
                "window_seconds": window_seconds,
                "retention_seconds": self.retention_seconds,
                "max_rows": self.max_rows,
                "started_at": self.started_at,
                "pruned_through": self._pruned_through,
                "capture_gap_through": self._capture_gap_through,
                "retained_sample": sample,
            }

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        # A dispatch snapshot may already hold this collector, but its closed
        # flag prevents any further capture. Never mutate SQLAlchemy's event
        # deques during a concurrent cursor execution.
        self._bridge.discard(self)


class SQLiteQueryMetrics(DatabaseQueryMetrics):
    """The same bounded window semantics for operation-scoped SQLite stores."""

    def __init__(self, retention_seconds: int = 604800, max_rows: int = 10000):
        super().__init__(None, retention_seconds, max_rows)

    def stats(self, window_seconds: int = 60) -> dict[str, Any]:
        return {
            **super().stats(window_seconds),
            "scope": "bound_auth_file_store_current_process",
            "latency_scope": "sqlite_execution_call_excludes_connect_and_fetch",
        }


class MeasuredSQLiteCursor(sqlite3.Cursor):
    def _execute(self, method: Any, *args: Any) -> Any:
        collectors = cast(MeasuredSQLiteConnection, self.connection).query_collectors
        starts = []
        for collector in collectors:
            try:
                starts.append((collector, time.perf_counter()))
            except Exception:
                collector._safe_gap()
        succeeded = False
        try:
            result = method(*args)
            succeeded = True
            return result
        finally:
            for collector, started in starts:
                try:
                    collector._record((time.perf_counter() - started) * 1000, succeeded)
                except Exception:
                    collector._safe_gap()

    def execute(self, *args: Any) -> Any:
        return self._execute(super().execute, *args)

    def executemany(self, *args: Any) -> Any:
        return self._execute(super().executemany, *args)

    def executescript(self, *args: Any) -> Any:
        # One script call is one sample, including partially failed scripts.
        return self._execute(super().executescript, *args)


class MeasuredSQLiteConnection(sqlite3.Connection):
    query_collectors: tuple[SQLiteQueryMetrics, ...] = ()

    def cursor(self, factory: Any = MeasuredSQLiteCursor) -> Any:
        return super().cursor(factory)

    def execute(self, *args: Any) -> Any:
        return self.cursor().execute(*args)

    def executemany(self, *args: Any) -> Any:
        return self.cursor().executemany(*args)

    def executescript(self, *args: Any) -> Any:
        return self.cursor().executescript(*args)
