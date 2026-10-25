"""Transactional auth storage, isolated from #151's business database.

Connections are operation-scoped. Sessions and rate limits remain effective
across restarts and multiple processes using the same database file.
"""

import hashlib
import os
import sqlite3
import threading
import time
import weakref
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from api.monitoring.database_metrics import MeasuredSQLiteConnection, SQLiteQueryMetrics


class AuthStore:
    def __init__(self, path: Path):
        self._query_metrics: weakref.WeakSet[SQLiteQueryMetrics] = weakref.WeakSet()
        self._query_metrics_lock = threading.Lock()
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Create with restrictive permissions before SQLite writes any secrets.
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS auth_users (
                    id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE,
                    email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
                    refresh_hash TEXT NOT NULL, expires_at INTEGER NOT NULL,
                    revoked INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS auth_keys (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES auth_users(id),
                    provider TEXT NOT NULL, key_name TEXT NOT NULL, ciphertext TEXT NOT NULL,
                    created_at INTEGER NOT NULL, last_used_at INTEGER,
                    usage_count INTEGER NOT NULL DEFAULT 0,
                    verification_count INTEGER NOT NULL DEFAULT 0,
                    last_verified_at INTEGER, verified INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS auth_keys_owner ON auth_keys(user_id);
                CREATE TABLE IF NOT EXISTS auth_user_api_calls (
                    user_id TEXT NOT NULL, period TEXT NOT NULL,
                    period_start INTEGER NOT NULL, count INTEGER NOT NULL,
                    PRIMARY KEY(user_id, period, period_start)
                );
                CREATE TABLE IF NOT EXISTS auth_rates (
                    bucket TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at INTEGER NOT NULL
                );
            """)
            columns = {row[1] for row in db.execute("PRAGMA table_info(auth_keys)").fetchall()}
            if "masked_preview" not in columns:
                db.execute("ALTER TABLE auth_keys ADD COLUMN masked_preview TEXT")

    @staticmethod
    def _api_call_periods(now: float) -> dict[str, tuple[datetime, datetime]]:
        day = datetime.fromtimestamp(now, timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        month = day.replace(day=1)
        next_month = (month.replace(day=28) + timedelta(days=4)).replace(day=1)
        return {
            "daily_api_calls": (day, day + timedelta(days=1)),
            "monthly_api_calls": (month, next_month),
        }

    def record_user_api_call(self, user_id: str) -> None:
        """Accumulate one completed generation attempt, atomically for both periods."""
        periods = self._api_call_periods(time.time())
        with self.connection() as db:
            db.executemany(
                "INSERT INTO auth_user_api_calls(user_id,period,period_start,count) VALUES (?,?,?,1) "
                "ON CONFLICT(user_id,period,period_start) DO UPDATE SET count=count+1",
                [
                    (user_id, period, int(start.timestamp()))
                    for period, (start, _) in periods.items()
                ],
            )

    def reserve_user_api_call(
        self, user_id: str, daily_limit: int | None, monthly_limit: int | None
    ) -> tuple[str, int] | None:
        """Atomically admit one SDK attempt, or return the exhausted period/reset.

        IMMEDIATE serializes check-and-increment across processes. Compute the
        calendar after acquiring the lock so a wait across midnight is safe.
        """
        limits = dict(zip(("daily_api_calls", "monthly_api_calls"), (daily_limit, monthly_limit)))
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            periods = self._api_call_periods(time.time())
            for period, (start, end) in periods.items():
                row = db.execute(
                    "SELECT count FROM auth_user_api_calls WHERE user_id=? AND period=? AND period_start=?",
                    (user_id, period, int(start.timestamp())),
                ).fetchone()
                limit = limits[period]
                if limit is not None and (row[0] if row else 0) >= limit:
                    return period, int(end.timestamp())
            db.executemany(
                "INSERT INTO auth_user_api_calls(user_id,period,period_start,count) VALUES (?,?,?,1) "
                "ON CONFLICT(user_id,period,period_start) DO UPDATE SET count=count+1",
                [
                    (user_id, period, int(start.timestamp()))
                    for period, (start, _) in periods.items()
                ],
            )
        return None

    def user_api_calls(
        self, user_id: str, daily_limit: int | None = None, monthly_limit: int | None = None
    ) -> dict[str, Any]:
        """Read a consistent snapshot of current UTC calendar buckets."""
        periods = self._api_call_periods(time.time())
        with self.connection() as db:
            rows = db.execute(
                "SELECT period,count FROM auth_user_api_calls WHERE user_id=? AND "
                "((period='daily_api_calls' AND period_start=?) OR "
                "(period='monthly_api_calls' AND period_start=?))",
                (
                    user_id,
                    int(periods["daily_api_calls"][0].timestamp()),
                    int(periods["monthly_api_calls"][0].timestamp()),
                ),
            ).fetchall()
        counts = dict(rows)
        result = {
            period: {
                "status": "metered",
                "limit": None,
                "remaining": None,
                "used": counts.get(period, 0),
                "timezone": "UTC",
                "period_start": start.isoformat(),
                "resets_at": end.isoformat(),
                "scope": "owned_generation_sdk_attempts",
                "collection_mode": "best_effort_since_instrumentation",
            }
            for period, (start, end) in periods.items()
        }
        for period, limit in zip(periods, (daily_limit, monthly_limit)):
            if daily_limit is not None or monthly_limit is not None:
                result[period]["collection_mode"] = "atomic_before_sdk_attempt"
            if limit is not None:
                result[period].update(
                    status="enforced", limit=limit, remaining=max(0, limit - counts.get(period, 0))
                )
        return result

    def attach_query_metrics(self, metrics: SQLiteQueryMetrics) -> None:
        with self._query_metrics_lock:
            self._query_metrics.add(metrics)

    def detach_query_metrics(self, metrics: SQLiteQueryMetrics) -> None:
        with self._query_metrics_lock:
            self._query_metrics.discard(metrics)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=10, factory=MeasuredSQLiteConnection)
        with self._query_metrics_lock:
            db.query_collectors = tuple(self._query_metrics)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def user(self, user_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM auth_users WHERE id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def find_user(self, identity: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM auth_users WHERE username=? OR email=?",
                (identity.casefold(), identity.casefold()),
            ).fetchone()
            return dict(row) if row else None

    def add_user(self, user_id: str, username: str, email: str, password_hash: str) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO auth_users VALUES (?, ?, ?, ?, ?)",
                (user_id, username.casefold(), email.casefold(), password_hash, int(time.time())),
            )

    def update_password(self, user_id: str, password_hash: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE auth_users SET password_hash=? WHERE id=?",
                (password_hash, user_id),
            )

    def update_user(self, user_id: str, username: str | None, email: str | None) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE auth_users SET username=COALESCE(?,username), email=COALESCE(?,email) WHERE id=?",
                (
                    username.casefold() if username else None,
                    email.casefold() if email else None,
                    user_id,
                ),
            )

    def add_session(self, sid: str, user_id: str, refresh_hash: str, expires_at: int) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=?", (int(time.time()),))
            db.execute(
                "INSERT INTO auth_sessions VALUES (?, ?, ?, ?, 0)",
                (sid, user_id, refresh_hash, expires_at),
            )

    def session(self, sid: str, user_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM auth_sessions WHERE id=? AND user_id=? AND revoked=0 AND expires_at>?",
                (sid, user_id, int(time.time())),
            ).fetchone()
            return dict(row) if row else None

    def rotate(self, sid: str, user_id: str, old_hash: str, new_hash: str) -> bool:
        with self.connection() as db:
            return (
                db.execute(
                    "UPDATE auth_sessions SET refresh_hash=? WHERE id=? AND user_id=? AND refresh_hash=? AND revoked=0 AND expires_at>?",
                    (new_hash, sid, user_id, old_hash, int(time.time())),
                ).rowcount
                == 1
            )

    def revoke(self, sid: str, user_id: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE auth_sessions SET revoked=1 WHERE id=? AND user_id=?", (sid, user_id)
            )

    def allow(self, bucket: str, limit: int, window: int) -> tuple[bool, int]:
        now = int(time.time())
        bucket = hashlib.sha256(bucket.encode("utf-8")).hexdigest()
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM auth_rates WHERE expires_at<=?", (now,))
            row = db.execute("SELECT * FROM auth_rates WHERE bucket=?", (bucket,)).fetchone()
            if row and row["count"] >= limit:
                return False, max(1, row["expires_at"] - now)
            if row:
                db.execute("UPDATE auth_rates SET count=count+1 WHERE bucket=?", (bucket,))
            else:
                db.execute("INSERT INTO auth_rates VALUES (?, 1, ?)", (bucket, now + window))
        return True, 0

    def add_key(
        self,
        key_id: str,
        user_id: str,
        provider: str,
        name: str,
        ciphertext: str,
        masked_preview: str,
    ) -> None:
        with self.connection() as db:
            db.execute(
                "INSERT INTO auth_keys(id,user_id,provider,key_name,ciphertext,created_at,masked_preview) VALUES (?,?,?,?,?,?,?)",
                (
                    key_id,
                    user_id,
                    provider,
                    name,
                    ciphertext,
                    int(time.time()),
                    masked_preview,
                ),
            )

    def key(self, key_id: str, user_id: str) -> dict[str, Any] | None:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM auth_keys WHERE id=? AND user_id=?", (key_id, user_id)
            ).fetchone()
            return dict(row) if row else None

    def keys(self, user_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM auth_keys WHERE user_id=? ORDER BY created_at,id", (user_id,)
                )
            ]

    def update_key(
        self,
        key_id: str,
        user_id: str,
        name: str | None,
        ciphertext: str | None,
        masked_preview: str | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE auth_keys SET key_name=COALESCE(?,key_name), ciphertext=COALESCE(?,ciphertext), masked_preview=COALESCE(?,masked_preview), verified=CASE WHEN ? IS NULL THEN verified ELSE 0 END WHERE id=? AND user_id=?",
                (name, ciphertext, masked_preview, ciphertext, key_id, user_id),
            )

    def delete_key(self, key_id: str, user_id: str) -> None:
        with self.connection() as db:
            db.execute("DELETE FROM auth_keys WHERE id=? AND user_id=?", (key_id, user_id))

    def record_verification(self, key_id: str, user_id: str, ciphertext: str, ok: bool) -> None:
        with self.connection() as db:
            # A concurrent edit must not mark the replacement key as verified.
            db.execute(
                "UPDATE auth_keys SET verification_count=verification_count+1,last_verified_at=?,verified=? WHERE id=? AND user_id=? AND ciphertext=?",
                (int(time.time()), int(ok), key_id, user_id, ciphertext),
            )

    def record_key_usage(self, key_id: str, user_id: str) -> None:
        """Worker integration hook: call after a real provider request, not simulation."""
        with self.connection() as db:
            db.execute(
                "UPDATE auth_keys SET usage_count=usage_count+1,last_used_at=? WHERE id=? AND user_id=?",
                (int(time.time()), key_id, user_id),
            )
