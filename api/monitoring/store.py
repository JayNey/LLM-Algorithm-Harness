"""Bounded, persistent monitoring records in the authentication database.

The coverage watermark survives restarts and is shared by every API process.
When retention or the row limit discards requests in a queried window, totals
are unavailable; the response reports the retained sample separately.
"""

import json
import math
import sqlite3
import threading
import time
from collections.abc import Iterable, Mapping
from contextlib import AbstractContextManager
from typing import Any, BinaryIO

from api.auth.store import AuthStore
from src.utils.secrets import REDACTED, is_sensitive_key, redact_sensitive_text

_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_MAX_MESSAGE = 4096
_MAX_CONTEXT_BYTES = 16384


def _bounded_text(value: str, limit: int, secrets: tuple[str, ...]) -> str:
    return redact_sensitive_text(value, secrets)[:limit]


def _safe_context(
    value: Any, secrets: tuple[str, ...], depth: int = 0, budget: list[int] | None = None
) -> Any:
    """Redact before truncating text and bound recursive/untrusted log context."""
    if budget is None:
        budget = [512]
    if depth >= 6 or budget[0] <= 0:
        return "[TRUNCATED]"
    budget[0] -= 1
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for i, (key, item) in enumerate(value.items()):
            if i >= 64 or budget[0] <= 0:
                result["_truncated"] = True
                break
            sensitive = is_sensitive_key(key)
            key = _bounded_text(str(key), 128, secrets)
            result[key] = (
                REDACTED
                if sensitive and item is not None and item != ""
                else _safe_context(item, secrets, depth + 1, budget)
            )
        return result
    if isinstance(value, (list, tuple)):
        items = []
        for i, item in enumerate(value):
            if i >= 64 or budget[0] <= 0:
                items.append("[TRUNCATED]")
                break
            items.append(_safe_context(item, secrets, depth + 1, budget))
        return items
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else "[NONFINITE]"
    # SecretStr.__str__ conceals its value; unknown objects are not serialized.
    if isinstance(value, str):
        return _bounded_text(value, _MAX_MESSAGE, secrets)
    return "[UNSUPPORTED]"


class MonitorStore:
    def __init__(
        self, auth_store: AuthStore, retention_seconds: int = 604800, max_rows: int = 10000
    ):
        if retention_seconds < 1 or max_rows < 1:
            raise ValueError("Monitoring retention and row limit must be positive")
        self.auth_store = auth_store
        self.retention_seconds = retention_seconds
        self.max_rows = max_rows
        self._capture_gap_through = 0.0
        self._gap_lock = threading.Lock()
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS api_monitor_meta (
                    key TEXT PRIMARY KEY, value REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_monitor_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL, method TEXT NOT NULL, route TEXT NOT NULL,
                    status_code INTEGER NOT NULL, duration_ms REAL NOT NULL, user_id TEXT
                );
                CREATE INDEX IF NOT EXISTS api_monitor_requests_time
                    ON api_monitor_requests(timestamp);
                CREATE INDEX IF NOT EXISTS api_monitor_requests_owner
                    ON api_monitor_requests(user_id,timestamp);
                CREATE TABLE IF NOT EXISTS api_monitor_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL, level TEXT NOT NULL, message TEXT NOT NULL,
                    user_id TEXT, run_id TEXT, context TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS api_monitor_logs_time ON api_monitor_logs(timestamp);
                CREATE INDEX IF NOT EXISTS api_monitor_logs_owner
                    ON api_monitor_logs(user_id,run_id,timestamp);
            """)
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO api_monitor_meta(key,value) VALUES ('started_at',?)",
                (time.time(),),
            )
            db.execute(
                "INSERT OR IGNORE INTO api_monitor_meta(key,value) VALUES ('pruned_through',0)"
            )
            db.execute(
                "INSERT OR IGNORE INTO api_monitor_meta(key,value) VALUES ('capture_gap_through',0)"
            )
            self._prune(db, time.time())

    def connection(self) -> AbstractContextManager[sqlite3.Connection]:
        return self.auth_store.connection()

    def record_llm_call(self, succeeded: bool, duration_ms: float) -> None:
        """Atomically accumulate completed SDK attempts, without request data."""
        if (
            type(succeeded) is not bool
            or isinstance(duration_ms, bool)
            or not math.isfinite(duration_ms)
            or duration_ms < 0
        ):
            raise ValueError("Invalid LLM monitoring measurement")
        with self.connection() as db:
            # Monitoring contention must not impose the normal auth DB wait.
            db.execute("PRAGMA busy_timeout=100")
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT OR IGNORE INTO api_monitor_meta(key,value) VALUES ('llm_started_at',?)",
                (time.time(),),
            )
            db.executemany(
                "INSERT INTO api_monitor_meta(key,value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=value+excluded.value",
                [
                    ("llm_total_calls", 1),
                    ("llm_successful_calls", int(succeeded)),
                    ("llm_failed_calls", int(not succeeded)),
                    ("llm_duration_ms", duration_ms),
                ],
            )

    def llm_stats(self) -> dict[str, Any]:
        """One SELECT provides a coherent snapshot across concurrent writers."""
        with self.connection() as db:
            meta = dict(db.execute("SELECT key,value FROM api_monitor_meta WHERE key LIKE 'llm_%'"))
        count = int(meta.get("llm_total_calls", 0))
        successes = int(meta.get("llm_successful_calls", 0))
        return {
            "status": "ok",
            "source": "persisted_llm_attempts",
            "scope": "recorded_completed_attempts_shared_auth_database",
            "collection_mode": "best_effort",
            "started_at": meta.get("llm_started_at"),
            "total_calls": count,
            "successful_calls": successes,
            "failed_calls": int(meta.get("llm_failed_calls", 0)),
            "success_rate": successes / count if count else None,
            "avg_latency_ms": meta["llm_duration_ms"] / count if count else None,
            "detail": (
                "Recorded completed SDK generation attempts since started_at; retries count "
                "separately. Excludes cache hits, verification, backoff and collection overhead. "
                "Unconfigured clients, capture failures and interrupted requests may be absent."
            ),
        }

    def _prune(self, db: sqlite3.Connection, now: float) -> None:
        self._flush_capture_gap(db)
        # SQL identifiers come solely from these two literal table names.
        for table in ("api_monitor_requests", "api_monitor_logs"):
            expired = db.execute(
                f"SELECT MAX(timestamp) FROM {table} WHERE timestamp<?",
                (now - self.retention_seconds,),
            ).fetchone()[0]
            db.execute(f"DELETE FROM {table} WHERE timestamp<?", (now - self.retention_seconds,))
            overflow = db.execute(
                f"SELECT MAX(timestamp) FROM {table} WHERE id NOT IN "
                f"(SELECT id FROM {table} ORDER BY timestamp DESC,id DESC LIMIT ?)",
                (self.max_rows,),
            ).fetchone()[0]
            db.execute(
                f"DELETE FROM {table} WHERE id NOT IN "
                f"(SELECT id FROM {table} ORDER BY timestamp DESC,id DESC LIMIT ?)",
                (self.max_rows,),
            )
            if table == "api_monitor_requests":
                watermark = max(expired or 0, overflow or 0)
                db.execute(
                    "UPDATE api_monitor_meta SET value=MAX(value,?) WHERE key='pruned_through'",
                    (watermark,),
                )

    def _flush_capture_gap(self, db: sqlite3.Connection) -> None:
        with self._gap_lock:
            watermark = self._capture_gap_through
        if watermark:
            db.execute(
                "UPDATE api_monitor_meta SET value=MAX(value,?) WHERE key='capture_gap_through'",
                (watermark,),
            )

    def mark_capture_gap(self, timestamp: float | None = None) -> None:
        """Invalidate incomplete request windows after a capture failure.

        The in-process watermark is flushed after database recovery. If the
        process is killed while the database is completely unwritable, that
        unflushed watermark cannot be recovered after restart.
        """
        when = time.time() if timestamp is None else timestamp
        if not math.isfinite(when) or when < 0:
            raise ValueError("Invalid capture gap timestamp")
        with self._gap_lock:
            self._capture_gap_through = max(self._capture_gap_through, when)
        try:
            with self.connection() as db:
                db.execute("BEGIN IMMEDIATE")
                self._flush_capture_gap(db)
        except Exception:
            # The same failed database must not prevent an original response.
            pass

    def record_request(
        self,
        method: str,
        route: str,
        status_code: int,
        duration_ms: float,
        user_id: str | None = None,
    ) -> None:
        if not 100 <= status_code <= 599 or not math.isfinite(duration_ms) or duration_ms < 0:
            raise ValueError("Invalid request monitoring measurement")
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO api_monitor_requests(timestamp,method,route,status_code,duration_ms,user_id) "
                "VALUES (?,?,?,?,?,?)",
                (now, method.upper()[:16], route[:256], status_code, duration_ms, user_id),
            )
            self._prune(db, now)

    @staticmethod
    def _request_summary(rows: list[sqlite3.Row], window_seconds: int) -> dict[str, Any]:
        durations = sorted(row["duration_ms"] for row in rows)
        count = len(rows)
        errors = sum(row["status_code"] >= 400 for row in rows)
        return {
            "request_count": count,
            "errors": errors,
            "error_rate": errors / count if count else None,
            "avg_response_time_ms": sum(durations) / count if count else None,
            "p95_response_time_ms": durations[math.ceil(0.95 * count) - 1] if count else None,
            "requests_per_second": count / window_seconds,
        }

    def api_stats(self, window_seconds: int = 60, user_id: str | None = None) -> dict[str, Any]:
        if window_seconds < 1:
            raise ValueError("Statistics window must be positive")
        now = time.time()
        start = now - window_seconds
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._prune(db, now)
            meta = dict(db.execute("SELECT key,value FROM api_monitor_meta"))
            where = "timestamp>=? AND timestamp<=?"
            parameters: list[Any] = [start, now]
            if user_id is not None:
                where += " AND user_id=?"
                parameters.append(user_id)
            rows = db.execute(
                f"SELECT method,route,status_code,duration_ms FROM api_monitor_requests WHERE {where}",
                parameters,
            ).fetchall()
        complete = (
            meta["started_at"] <= start
            and meta["pruned_through"] < start
            and meta["capture_gap_through"] < start
            and window_seconds <= self.retention_seconds
        )
        sample = self._request_summary(rows, window_seconds)
        grouped: dict[tuple[str, str], list[sqlite3.Row]] = {}
        for row in rows:
            grouped.setdefault((row["method"], row["route"]), []).append(row)
        endpoints = []
        for (method, route), endpoint_rows in sorted(grouped.items()):
            retained = self._request_summary(endpoint_rows, window_seconds)
            retained["count"] = retained.pop("request_count")
            endpoints.append(
                {
                    "method": method,
                    "route": route,
                    **(retained if complete else {key: None for key in retained}),
                    "window_complete": complete,
                    "retained_sample": retained,
                }
            )
        return {
            **(sample if complete else {key: None for key in sample}),
            "source": "persisted_requests" if complete else "retained_sample",
            "window_complete": complete,
            "window_seconds": window_seconds,
            "retention_seconds": self.retention_seconds,
            "max_rows": self.max_rows,
            "started_at": meta["started_at"],
            "pruned_through": meta["pruned_through"] or None,
            "capture_gap_through": meta["capture_gap_through"] or None,
            "retained_sample": sample,
            "endpoints": endpoints,
        }

    def append_log(
        self,
        level: str,
        message: str,
        user_id: str | None = None,
        run_id: str | None = None,
        context: Any = None,
        known_secrets: Iterable[str] = (),
    ) -> None:
        level = level.upper()
        if level == "WARN":
            level = "WARNING"
        if level not in _LEVELS:
            raise ValueError("Unknown log level")
        secrets = tuple(known_secrets)
        context_json = json.dumps(
            _safe_context({} if context is None else context, secrets), ensure_ascii=False
        )
        if len(context_json.encode("utf-8")) > _MAX_CONTEXT_BYTES:
            context_json = '{"_truncated":true}'
        now = time.time()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO api_monitor_logs(timestamp,level,message,user_id,run_id,context) "
                "VALUES (?,?,?,?,?,?)",
                (
                    now,
                    level,
                    _bounded_text(message, _MAX_MESSAGE, secrets),
                    # These trusted public identifiers are ownership selectors;
                    # a one-character provider key must not rewrite their UUIDs.
                    user_id[:128] if user_id else None,
                    run_id[:128] if run_id else None,
                    context_json,
                ),
            )
            self._prune(db, now)

    def query_logs(
        self,
        level: str | None = None,
        start: float | None = None,
        end: float | None = None,
        search: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        if not 1 <= limit <= 1000 or offset < 0:
            raise ValueError("Invalid log pagination")
        where, parameters = self._log_filters(level, start, end, search, user_id, run_id)
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._prune(db, time.time())
            total = db.execute(
                f"SELECT COUNT(*) FROM api_monitor_logs WHERE {where}", parameters
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM api_monitor_logs WHERE {where} ORDER BY timestamp DESC,id DESC LIMIT ? OFFSET ?",
                [*parameters, limit, offset],
            ).fetchall()
        result = []
        for row in rows:
            record = dict(row)
            record["context"] = json.loads(record["context"])
            result.append(record)
        return result, total

    @staticmethod
    def _log_filters(
        level: str | None,
        start: float | None,
        end: float | None,
        search: str | None,
        user_id: str | None,
        run_id: str | None,
    ) -> tuple[str, list[Any]]:
        if start is not None and (not math.isfinite(start) or start < 0):
            raise ValueError("Invalid start time")
        if end is not None and (not math.isfinite(end) or end < 0):
            raise ValueError("Invalid end time")
        if start is not None and end is not None and start > end:
            raise ValueError("Start time must precede end time")
        clauses: list[str] = []
        parameters: list[Any] = []
        for column, value in (("level", level), ("user_id", user_id), ("run_id", run_id)):
            if value is not None:
                clauses.append(f"{column}=?")
                normalized = value.upper() if column == "level" else value
                parameters.append(
                    "WARNING" if column == "level" and normalized == "WARN" else normalized
                )
        if start is not None:
            clauses.append("timestamp>=?")
            parameters.append(start)
        if end is not None:
            clauses.append("timestamp<=?")
            parameters.append(end)
        if search is not None:
            clauses.append("instr(message,?)>0")
            parameters.append(search)
        where = " AND ".join(clauses) or "1=1"
        return where, parameters

    def export_logs(
        self,
        stream: BinaryIO,
        level: str | None = None,
        start: float | None = None,
        end: float | None = None,
        search: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
        max_bytes: int = 32 * 1024 * 1024,
    ) -> dict[str, Any]:
        """Write bounded JSONL from one transaction snapshot into an owned stream."""
        if max_bytes < 1:
            raise ValueError("Log export byte limit must be positive")
        where, parameters = self._log_filters(level, start, end, search, user_id, run_id)
        exported, consumed = 0, 0
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self._prune(db, time.time())
            total = db.execute(
                f"SELECT COUNT(*) FROM api_monitor_logs WHERE {where}", parameters
            ).fetchone()[0]
            rows = db.execute(
                f"SELECT * FROM api_monitor_logs WHERE {where} ORDER BY timestamp DESC,id DESC",
                parameters,
            )
            for row in rows:
                record = dict(row)
                record["context"] = json.loads(record["context"])
                chunk = (json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n").encode(
                    "utf-8"
                )
                if consumed + len(chunk) > max_bytes:
                    break
                stream.write(chunk)
                consumed += len(chunk)
                exported += 1
        return {"total": total, "exported": exported, "truncated": exported < total}
