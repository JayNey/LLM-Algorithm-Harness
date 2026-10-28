"""Transactional file metadata and per-user datasets in a separate namespace."""

import json
import sqlite3
import time
import uuid
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, cast

from fastapi import HTTPException
from pydantic_settings import BaseSettings, SettingsConfigDict

from api.auth.store import AuthStore


class _FileDatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    AUTH_DATABASE_PATH: Path = Path("data/auth/auth.sqlite3")


class FileStore:
    @classmethod
    def from_environment(cls) -> "FileStore":
        """Resolve the same metadata database in API and worker processes."""
        return cls(AuthStore(_FileDatabaseSettings().AUTH_DATABASE_PATH))

    def __init__(self, auth_store: AuthStore):
        self.auth_store = auth_store
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS api_file_runs (
                    run_id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    deleted INTEGER NOT NULL DEFAULT 0, result_file_id TEXT
                );
                CREATE TABLE IF NOT EXISTS api_file_objects (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL,
                    filename TEXT NOT NULL, relative_path TEXT NOT NULL UNIQUE,
                    suffix TEXT NOT NULL, category TEXT NOT NULL,
                    size INTEGER NOT NULL, sha256 TEXT NOT NULL,
                    created_at INTEGER NOT NULL, expires_at INTEGER,
                    run_id TEXT, deleted INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS api_file_objects_owner ON api_file_objects(user_id);
                CREATE INDEX IF NOT EXISTS api_file_objects_run ON api_file_objects(run_id,user_id);
                CREATE TABLE IF NOT EXISTS api_file_datasets (
                    user_id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS api_file_jobs (
                    id TEXT PRIMARY KEY, user_id TEXT NOT NULL, file_id TEXT NOT NULL,
                    mode TEXT NOT NULL, status TEXT NOT NULL,
                    processed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL, result TEXT
                );
                CREATE INDEX IF NOT EXISTS api_file_jobs_source ON api_file_jobs(file_id,status);
            """)

    def connection(self) -> AbstractContextManager[sqlite3.Connection]:
        return self.auth_store.connection()

    def owned_file(self, file_id: str, user_id: str, allow_expired: bool = False) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM api_file_objects WHERE id=? AND user_id=? AND deleted=0",
                (file_id, user_id),
            ).fetchone()
            if not row or (
                not allow_expired
                and row["expires_at"] is not None
                and row["expires_at"] <= int(time.time())
            ):
                raise HTTPException(404, "File not found")
            if row["run_id"] is not None:
                self.check_run(db, row["run_id"], user_id)
            return dict(row)

    @staticmethod
    def check_run(db: sqlite3.Connection, run_id: str, user_id: str) -> None:
        row = db.execute(
            "SELECT 1 FROM api_file_runs WHERE run_id=? AND user_id=? AND deleted=0",
            (run_id, user_id),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Result not found")

    def register_run(self, run_id: str, user_id: str) -> None:
        with self.connection() as db:
            db.execute("INSERT INTO api_file_runs(run_id,user_id) VALUES (?,?)", (run_id, user_id))

    def activate_result(self, run_id: str, user_id: str, file_id: str) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_run(db, run_id, user_id)
            old = db.execute(
                "SELECT result_file_id FROM api_file_runs WHERE run_id=?", (run_id,)
            ).fetchone()[0]
            db.execute(
                "UPDATE api_file_runs SET result_file_id=? WHERE run_id=? AND user_id=? AND deleted=0",
                (file_id, run_id, user_id),
            )
            if old:
                db.execute(
                    "UPDATE api_file_objects SET deleted=1 WHERE id=? AND user_id=?", (old, user_id)
                )

    def result_file(self, run_id: str, user_id: str) -> dict[str, Any]:
        with self.connection() as db:
            self.check_run(db, run_id, user_id)
            row = db.execute(
                "SELECT result_file_id FROM api_file_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        if not row[0]:
            raise HTTPException(404, "Result not available")
        return self.owned_file(row[0], user_id)

    def add_file(self, record: dict[str, Any], max_user_bytes: int) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if record["run_id"] is not None:
                self.check_run(db, record["run_id"], record["user_id"])
            total = db.execute(
                "SELECT COALESCE(SUM(size),0) FROM api_file_objects WHERE user_id=?",
                (record["user_id"],),
            ).fetchone()[0]
            if total + record["size"] > max_user_bytes:
                raise HTTPException(413, "User file storage limit exceeded")
            db.execute(
                "INSERT INTO api_file_objects(id,user_id,filename,relative_path,suffix,category,size,sha256,created_at,expires_at,run_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                tuple(
                    record[k]
                    for k in [
                        "id",
                        "user_id",
                        "filename",
                        "relative_path",
                        "suffix",
                        "category",
                        "size",
                        "sha256",
                        "created_at",
                        "expires_at",
                        "run_id",
                    ]
                ),
            )

    def dataset(self, user_id: str) -> list[dict[str, Any]]:
        with self.connection() as db:
            row = db.execute(
                "SELECT payload FROM api_file_datasets WHERE user_id=?", (user_id,)
            ).fetchone()
            return cast(list[dict[str, Any]], json.loads(row["payload"])) if row else []

    def create_job(self, file_id: str, user_id: str, mode: str, max_active: int = 8) -> str:
        job_id, now = str(uuid.uuid4()), int(time.time())
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM api_file_objects WHERE id=? AND user_id=? AND deleted=0 AND (expires_at IS NULL OR expires_at>?)",
                (file_id, user_id, now),
            ).fetchone()
            if not row or row["suffix"] not in {".json", ".csv"} or row["category"] != "upload":
                raise HTTPException(404, "Importable upload not found")
            active = db.execute(
                "SELECT 1 FROM api_file_jobs WHERE file_id=? AND status IN ('pending','running')",
                (file_id,),
            ).fetchone()
            if active:
                raise HTTPException(409, "File is already being imported")
            pending = db.execute(
                "SELECT COUNT(*) FROM api_file_jobs WHERE status IN ('pending','running')"
            ).fetchone()[0]
            if pending >= max_active:
                raise HTTPException(429, "Import capacity reached", headers={"Retry-After": "1"})
            db.execute(
                "INSERT INTO api_file_jobs(id,user_id,file_id,mode,status,created_at,updated_at) VALUES (?,?,?,?,'pending',?,?)",
                (job_id, user_id, file_id, mode, now, now),
            )
        return job_id

    def job(self, job_id: str, user_id: str) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM api_file_jobs WHERE id=? AND user_id=?", (job_id, user_id)
            ).fetchone()
            if not row:
                raise HTTPException(404, "Import job not found")
            result = dict(row)
            result["result"] = json.loads(result["result"]) if result["result"] else None
            return result

    def claim_job(self, job_id: str, user_id: str) -> bool:
        with self.connection() as db:
            return (
                db.execute(
                    "UPDATE api_file_jobs SET status='running',updated_at=? WHERE id=? AND user_id=? AND status='pending'",
                    (int(time.time()), job_id, user_id),
                ).rowcount
                == 1
            )

    def progress(self, job_id: str, processed: int, total: int) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE api_file_jobs SET processed=?,total=?,updated_at=? WHERE id=? AND status IN ('running','paused')",
                (processed, total, int(time.time()), job_id),
            )

    def pause_job(self, job_id: str) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE api_file_jobs SET status='paused',updated_at=? WHERE id=? AND status='running'",
                (int(time.time()), job_id),
            )

    def sync_task_status(
        self, job_id: str, user_id: str, status: str, expected_status: str | None = None
    ) -> str | None:
        """Mirror lifecycle without replacing validation checkpoints or results."""
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE api_file_jobs SET status=?,updated_at=? WHERE id=? AND user_id=? AND status NOT IN ('completed','failed','cancelled') AND (? IS NULL OR status=?)",
                (status, int(time.time()), job_id, user_id, expected_status, expected_status),
            )
            row = db.execute(
                "SELECT status FROM api_file_jobs WHERE id=? AND user_id=?", (job_id, user_id)
            ).fetchone()
            return row["status"] if row is not None else None

    def restore_task_status(self, job_id: str, user_id: str, expected: str, previous: str) -> None:
        """Compensate a failed business commit without touching a newer transition."""
        with self.connection() as db:
            db.execute(
                "UPDATE api_file_jobs SET status=?,updated_at=? WHERE id=? AND user_id=? AND status=?",
                (previous, int(time.time()), job_id, user_id, expected),
            )

    def fail_job(self, job_id: str, details: dict[str, Any]) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE api_file_jobs SET status='failed',result=?,updated_at=? WHERE id=? AND status IN ('pending','running')",
                (
                    json.dumps(details, ensure_ascii=False, allow_nan=False),
                    int(time.time()),
                    job_id,
                ),
            )

    def merge_dataset(
        self,
        job_id: str,
        user_id: str,
        problems: list[dict[str, Any]],
        report: dict[str, Any],
        max_bytes: int,
        max_items: int,
    ) -> dict[str, Any]:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            job = db.execute(
                "SELECT * FROM api_file_jobs WHERE id=? AND user_id=? AND status='running'",
                (job_id, user_id),
            ).fetchone()
            if not job:
                raise HTTPException(409, "Import job is no longer active")
            old = db.execute(
                "SELECT payload FROM api_file_datasets WHERE user_id=?", (user_id,)
            ).fetchone()
            dataset = json.loads(old["payload"]) if old and job["mode"] == "append" else []
            by_id = {p["problem_id"]: p for p in dataset}
            duplicates = 0
            for problem in problems:
                if problem["problem_id"] in by_id:
                    duplicates += 1
                else:
                    by_id[problem["problem_id"]] = problem
            payload = json.dumps(list(by_id.values()), ensure_ascii=False, allow_nan=False)
            if len(payload.encode("utf-8")) > max_bytes or len(by_id) > max_items:
                raise HTTPException(413, "Merged dataset exceeds limit")
            result = {
                **report,
                "duplicates": duplicates,
                "imported": len(problems) - duplicates,
                "dataset_total": len(by_id),
            }
            now = int(time.time())
            db.execute(
                "INSERT INTO api_file_datasets VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
                (user_id, payload, now),
            )
            db.execute(
                "UPDATE api_file_jobs SET status='completed',processed=total,result=?,updated_at=? WHERE id=? AND user_id=?",
                (json.dumps(result, ensure_ascii=False, allow_nan=False), now, job_id, user_id),
            )
            return result

    def mark_file_deleted(self, file_id: str, user_id: str) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute(
                "SELECT 1 FROM api_file_jobs WHERE file_id=? AND status IN ('pending','running')",
                (file_id,),
            ).fetchone():
                raise HTTPException(409, "File is being imported")
            db.execute(
                "UPDATE api_file_objects SET deleted=1 WHERE id=? AND user_id=?", (file_id, user_id)
            )

    def mark_run_deleted(self, run_id: str, user_id: str) -> None:
        with self.connection() as db:
            db.execute("BEGIN IMMEDIATE")
            self.check_run(db, run_id, user_id)
            db.execute(
                "UPDATE api_file_runs SET deleted=1 WHERE run_id=? AND user_id=?", (run_id, user_id)
            )
            db.execute(
                "UPDATE api_file_objects SET deleted=1 WHERE run_id=? AND user_id=?",
                (run_id, user_id),
            )
