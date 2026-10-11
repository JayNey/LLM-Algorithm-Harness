"""Monitoring composition, trustworthy worker hooks and enforced quota views."""

import time
from typing import Any

from fastapi import HTTPException

from api.auth.service import AuthService, digest
from api.files.service import FileService
from api.monitoring.config import MonitorSettings
from api.monitoring.probes import MonitorProbes
from api.monitoring.store import MonitorStore
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
    ):
        self.auth, self.files, self.evaluations, self.settings = auth, files, evaluations, settings
        self.store = MonitorStore(
            auth.store, settings.MONITOR_RETENTION_SECONDS, settings.MONITOR_MAX_ROWS
        )
        self.probes = MonitorProbes(auth, files, settings)
        self.started = time.monotonic()
        self.cache: LLMResponseCache | None = None  # Bound explicitly by a real worker.

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

    def task_snapshot(self, state: str | None = None) -> dict[str, Any]:
        with self.evaluations._tasks_lock:
            tasks = list(self.evaluations.tasks.values())
            items = []
            for task in tasks:
                with task._lock:
                    if state and task.status != state:
                        continue
                    items.append(
                        {
                            "task_id": task.task_id,
                            "owner_id": task.owner_id,
                            "status": task.status,
                            "completed": task.completed_count,
                            "total": task.problem_count,
                        }
                    )
        return {
            "source": "in_process_evaluation_simulator",
            "items": items,
            "total": len(items),
            "production_queue_configured": False,
        }

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
            else "partial"
        )
        return {
            "status": status,
            "scope": "configured_api_foundation",
            "checks": checks,
            "pending_issues": [149, 151],
        }

    def performance(self) -> dict[str, Any]:
        return {
            "api": self.store.api_stats(self.settings.MONITOR_API_WINDOW_SECONDS),
            "evaluations": {
                "status": "not_configured",
                "avg_execution_time_seconds": None,
                "success_rate": None,
                "detail": "Real worker instrumentation awaits #149",
            },
            "database_queries": {
                "status": "not_configured",
                "avg_latency_ms": None,
                "detail": "Business database awaits #151",
            },
            "llm": self.llm_stats(),
        }

    def llm_stats(self) -> dict[str, Any]:
        with self.auth.store.connection() as db:
            row = db.execute(
                "SELECT COALESCE(SUM(usage_count),0),COALESCE(SUM(verification_count),0) FROM auth_keys"
            ).fetchone()
        return {
            "status": "not_configured",
            "source": "worker_instrumentation_pending_149",
            "total_calls": None,
            "success_rate": None,
            "avg_latency_ms": None,
            "recorded_usage_hooks": row[0],
            "key_verification_count": row[1],
            "detail": "Verification requests are not generation calls; usage hooks do not include latency",
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
