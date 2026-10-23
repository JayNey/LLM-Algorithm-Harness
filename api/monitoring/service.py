"""Monitoring composition, trustworthy worker hooks and enforced quota views."""

import time
from typing import Any

from fastapi import HTTPException
from sqlalchemy import Engine, case, func, select

from api.auth.service import AuthService, digest
from api.db.models import AsyncTask, Evaluation
from api.files.service import FileService
from api.monitoring.config import MonitorSettings
from api.monitoring.database_metrics import DatabaseQueryMetrics
from api.monitoring.execution_logs import task_log_key
from api.monitoring.probes import MonitorProbes
from api.monitoring.store import MonitorStore
from api.monitoring.task_snapshots import read_task_snapshot
from api.services import EvaluationService
from src.cache import LLMResponseCache
from src.task_service import TaskEvent


class MonitorService:
    def __init__(
        self,
        auth: AuthService,
        files: FileService,
        evaluations: EvaluationService,
        settings: MonitorSettings,
        *,
        task_engine: Engine | None = None,
    ):
        self.auth, self.files, self.evaluations, self.settings = auth, files, evaluations, settings
        self.store = MonitorStore(
            auth.store, settings.MONITOR_RETENTION_SECONDS, settings.MONITOR_MAX_ROWS
        )
        self.task_engine = task_engine if task_engine is not None else evaluations.engine
        self.probes = MonitorProbes(auth, files, settings, evaluations)
        self.database_metrics = DatabaseQueryMetrics(
            evaluations.engine, settings.MONITOR_RETENTION_SECONDS, settings.MONITOR_MAX_ROWS
        )
        self.started = time.monotonic()
        self.cache: LLMResponseCache | None = None  # Bound explicitly by a real worker.

    def close(self) -> None:
        self.probes.close()
        self.database_metrics.close()

    def known_secrets(self, user_id: str | None = None) -> list[str]:
        secrets = [
            self.auth.settings.SECRET_KEY.get_secret_value(),
            self.auth.settings.ENCRYPTION_KEY.get_secret_value(),
        ]
        if user_id:
            for record in self.auth.store.keys(user_id):
                try:
                    secrets.append(
                        self.auth.llm_config(
                            record["id"], user_id, "log-redaction"
                        ).api_key.get_secret_value()
                    )
                except HTTPException:
                    continue
        return secrets

    def audit_event(self, action: str, user_id: str, resource_id: str) -> None:
        run_id = resource_id if action.startswith("evaluation_") else None
        self.store.append_log(
            "INFO",
            action,
            user_id=user_id,
            run_id=run_id,
            context={"resource_id": resource_id, "source": "api_lifecycle"},
            known_secrets=self.known_secrets(user_id),
        )

    def record_task_event(self, event: TaskEvent, user_id: str) -> None:
        """Trusted #149 hook; never accept an HTTP owner claim or CLI path."""
        with self.files.store.connection() as db:
            self.files.store.check_run(db, event.run_id, user_id)
        level = "ERROR" if event.state == "failed" else "INFO"
        context = {
            "event_sequence": event.sequence,
            "event_timestamp": event.timestamp,
            "kind": event.kind,
            "state": event.state,
            "completed_units": event.completed_units,
            "total_units": event.total_units,
            "strategy": event.strategy,
            "problem_id": event.problem_id,
            "source": "task_service_event",
        }
        self.store.append_log(
            level,
            event.message or event.kind,
            user_id=user_id,
            run_id=event.run_id,
            context=context,
            known_secrets=self.known_secrets(user_id),
        )

    def owned_log_key(self, identifier: str, user_id: str) -> str:
        """Resolve actual queue identity before the legacy run mapping, without polling."""
        with self.task_engine.connect() as connection:
            task = (
                connection.execute(
                    select(AsyncTask.id, AsyncTask.user_id).where(AsyncTask.id == identifier)
                )
                .mappings()
                .first()
            )
            if task is not None:
                if task["user_id"] != user_id:
                    raise HTTPException(404, "Task not found")
                return task_log_key(task["id"])
            evaluation = (
                connection.execute(
                    select(Evaluation.id, Evaluation.user_id, Evaluation.async_task_id).where(
                        Evaluation.id == identifier
                    )
                )
                .mappings()
                .first()
            )
            if evaluation is not None:
                if evaluation["user_id"] != user_id:
                    raise HTTPException(404, "Task not found")
                if evaluation["async_task_id"]:
                    linked = connection.execute(
                        select(AsyncTask.id).where(
                            AsyncTask.id == evaluation["async_task_id"],
                            AsyncTask.user_id == user_id,
                            AsyncTask.entity_id == identifier,
                            AsyncTask.task_type == "evaluation",
                        )
                    ).scalar_one_or_none()
                    if linked is None:
                        raise HTTPException(404, "Task not found")
                    return task_log_key(linked)
        with self.files.store.connection() as db:
            self.files.store.check_run(db, identifier, user_id)
        return identifier

    def task_snapshot(
        self,
        state: str | None = None,
        limit: int = 100,
        offset: int = 0,
        task_source: str = "legacy_evaluation",
    ) -> dict[str, Any]:
        engine = self.task_engine if task_source == "async_task" else self.evaluations.engine
        return read_task_snapshot(engine, state, limit, offset, task_source)

    def health(self, include_sandbox: bool = False) -> dict[str, Any]:
        checks = {
            "database": self.probes.database(),
            "redis": self.probes.redis(),
            "workers": self.probes.workers(),
            "sandbox": (
                self.probes.sandbox()
                if include_sandbox
                else {
                    "status": "not_checked",
                    "detail": "Use the protected sandbox health endpoint",
                }
            ),
        }
        status = (
            "degraded"
            if any(item["status"] in {"unavailable", "unknown"} for item in checks.values())
            else "healthy" if all(item["status"] == "ok" for item in checks.values()) else "partial"
        )
        return {
            "status": status,
            "scope": "configured_api_foundation",
            "checks": checks,
            "pending_issues": [157],
        }

    def task_performance(self) -> dict[str, Any]:
        """Aggregate persisted worker lifecycles without polling Celery."""
        metadata = {
            "source": "persisted_async_tasks",
            "scope": "retained_business_tasks_all_time",
            "duration_scope": "first_start_to_final_end_includes_pause_and_retry",
            "success_rate_scope": "started_completed_over_started_completed_and_failed",
        }
        empty = {
            "completed": 0,
            "failed": 0,
            "duration_sample_count": 0,
            "avg_execution_time_seconds": None,
            "success_rate": None,
        }
        try:
            backend = self.task_engine.dialect.name
            if backend == "sqlite":
                seconds = (
                    func.julianday(AsyncTask.completed_at) - func.julianday(AsyncTask.started_at)
                ) * 86400.0
            elif backend == "postgresql":
                seconds = func.extract("epoch", AsyncTask.completed_at - AsyncTask.started_at)
            else:
                raise ValueError("Unsupported task metrics database")
            valid = AsyncTask.completed_at.is_not(None) & (
                AsyncTask.completed_at >= AsyncTask.started_at
            )
            query = (
                select(
                    AsyncTask.task_type,
                    func.sum(case((AsyncTask.status == "completed", 1), else_=0)).label(
                        "completed"
                    ),
                    func.sum(case((AsyncTask.status == "failed", 1), else_=0)).label("failed"),
                    func.count(case((valid, 1))).label("samples"),
                    func.sum(case((valid, seconds), else_=0.0)).label("seconds"),
                )
                .where(
                    AsyncTask.task_type.in_(("evaluation", "experiment", "benchmark", "import")),
                    AsyncTask.status.in_(("completed", "failed")),
                    AsyncTask.started_at.is_not(None),
                )
                .group_by(AsyncTask.task_type)
            )
            with self.task_engine.connect() as connection:
                rows = connection.execute(query).mappings().all()

            def aggregate(selected: list[Any]) -> dict[str, Any]:
                completed = sum(row["completed"] for row in selected)
                failed = sum(row["failed"] for row in selected)
                samples = sum(row["samples"] for row in selected)
                return {
                    **metadata,
                    "status": "ok",
                    "completed": completed,
                    "failed": failed,
                    "duration_sample_count": samples,
                    "avg_execution_time_seconds": (
                        float(sum(row["seconds"] for row in selected)) / samples
                        if samples
                        else None
                    ),
                    "success_rate": (
                        completed / (completed + failed) if completed + failed else None
                    ),
                }

            return {
                "tasks": aggregate(rows),
                "evaluations": aggregate([row for row in rows if row["task_type"] == "evaluation"]),
            }
        except Exception:
            unavailable = {
                **metadata,
                **{key: None for key in empty},
                "status": "unavailable",
                "detail": "Task performance could not be collected",
            }
            return {"tasks": unavailable, "evaluations": dict(unavailable)}

    def performance(self) -> dict[str, Any]:
        return {
            "api": self.store.api_stats(self.settings.MONITOR_API_WINDOW_SECONDS),
            **self.task_performance(),
            "database_queries": {
                **self.database_metrics.stats(self.settings.MONITOR_API_WINDOW_SECONDS),
                "engine_role": "evaluation_service",
            },
            "llm": self.llm_stats(),
        }

    def llm_stats(self) -> dict[str, Any]:
        with self.auth.store.connection() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(usage_count),0),COALESCE(SUM(verification_count),0) FROM auth_keys"
            ).fetchone()
        return {
            **self.store.llm_stats(),
            "recorded_usage_hooks": row[0],
            "key_verification_count": row[1],
        }

    def quotas(self, user_id: str) -> dict[str, Any]:
        now = int(time.time())
        with self.auth.store.connection() as db:
            files = db.execute(
                "SELECT COALESCE(SUM(size),0),COUNT(*) FROM api_file_objects WHERE user_id=?",
                (user_id,),
            ).fetchone()
            dataset = db.execute(
                "SELECT LENGTH(CAST(payload AS BLOB)),json_array_length(payload) FROM api_file_datasets WHERE user_id=?",
                (user_id,),
            ).fetchone()
            bucket = db.execute(
                "SELECT count,expires_at FROM auth_rates WHERE bucket=? AND expires_at>?",
                (digest("protected:" + user_id), now),
            ).fetchone()
            jobs = db.execute(
                "SELECT COUNT(*) FROM api_file_jobs WHERE user_id=? AND status IN ('pending','running')",
                (user_id,),
            ).fetchone()[0]
        return {
            "scope": "current_user_enforced_limits",
            "storage": {
                "used_bytes": files[0],
                "file_count": files[1],
                "limit_bytes": self.files.settings.FILE_MAX_USER_BYTES,
                "includes_pending_cleanup": True,
            },
            "dataset": {
                "used_bytes": dataset[0] if dataset else 0,
                "used_items": dataset[1] if dataset else 0,
                "limit_bytes": self.files.settings.FILE_UPLOAD_MAX_BYTES,
                "limit_items": self.files.settings.FILE_IMPORT_MAX_ITEMS,
                "separate_from_file_storage": True,
            },
            "protected_requests": {
                "used": bucket["count"] if bucket else 0,
                "limit": self.auth.settings.AUTH_PROTECTED_RATE_LIMIT,
                "window_seconds": self.auth.settings.AUTH_RATE_WINDOW_SECONDS,
                "resets_at": bucket["expires_at"] if bucket else None,
            },
            "imports": {
                "active_for_user": jobs,
                "global_active_limit": self.files.settings.FILE_MAX_ACTIVE_IMPORTS,
                "per_process_concurrency": self.files.settings.FILE_MAX_CONCURRENT_IMPORTS,
            },
            "transfers": {
                "per_process_concurrency": self.files.settings.FILE_MAX_CONCURRENT_TRANSFERS
            },
            "daily_api_calls": {"status": "not_configured", "limit": None, "used": None},
            "monthly_api_calls": {"status": "not_configured", "limit": None, "used": None},
        }
