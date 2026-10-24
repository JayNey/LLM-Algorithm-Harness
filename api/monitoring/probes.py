"""Real local probes with a small public surface and no provider network calls."""

import json
import math
import re
import shutil
import threading
import time
from pathlib import Path
from typing import Any, get_args

import psutil
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import select, text

from api.auth.service import AuthService
from api.db.migrate import SCRIPT_LOCATION
from api.db.models import Base
from api.files.service import FileService
from api.monitoring.config import MonitorSettings
from api.monitoring.containers import ContainerProbes
from api.monitoring.queue_health import QueueProbes
from api.services import EvaluationService
from src.cache import LLMResponseCache
from src.celery_app import celery_app
from src.harness import AlgorithmHarness
from src.models import LLMConfig, SandboxConfig, StrategyConfig
from src.sandbox_executor import SandboxExecutor

_CACHE_FIELDS = (
    "enabled",
    "total_entries",
    "disk_usage_mb",
    "hit_rate",
    "hits",
    "misses",
    "api_calls_saved",
)
_CATALOG_FILES = ("config.example.json", "config.siliconflow.example.json")
_MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+\-]{0,199}\Z")


def _unknown() -> dict[str, Any]:
    # Exceptions can contain local paths, connection strings or credentials.
    return {"status": "unknown", "detail": "Probe could not collect a measurement"}


class MonitorProbes:
    """Probe the services bound to this API process, without inventing dependencies."""

    def __init__(
        self,
        auth: AuthService,
        files: FileService,
        settings: MonitorSettings,
        evaluations: EvaluationService,
    ):
        self.auth = auth
        self.files = files
        self.settings = settings
        self.evaluations = evaluations
        self.queue = QueueProbes(settings, celery_app.conf.broker_url)
        self.container_resources = ContainerProbes(settings)
        self._sandbox_lock = threading.Lock()
        self._sandbox_result: dict[str, Any] | None = None
        self._sandbox_checked_at = 0.0

    def database(self) -> dict[str, Any]:
        """Check the actual SQLite connections and required tables, not a mock DB."""
        components: dict[str, Any] = {}
        for name, store, table in (
            ("authentication", self.auth.store, "auth_users"),
            ("files", self.files.store, "api_file_objects"),
        ):
            try:
                with store.connection() as db:
                    reachable = db.execute("SELECT 1").fetchone()[0] == 1
                    # LIMIT 0 verifies the schema while revealing no user records.
                    db.execute(f"SELECT 1 FROM {table} LIMIT 0").fetchall()
                components[name] = {
                    "status": "ok" if reachable else "unavailable",
                    "backend": "sqlite",
                }
            except Exception:
                components[name] = {
                    "status": "unavailable",
                    "backend": "sqlite",
                    "detail": "Local database probe failed",
                }
        business = self.business_database()
        return {
            "status": (
                "ok"
                if all(item["status"] == "ok" for item in (*components.values(), business))
                else "unavailable"
            ),
            **components,
            "business_database": business,
        }

    def business_database(self) -> dict[str, Any]:
        """Read the existing engine and migration metadata without recovery/DDL."""
        engine = self.evaluations.engine
        backend = (
            engine.dialect.name if engine.dialect.name in {"sqlite", "postgresql"} else "other"
        )
        metadata = {
            "backend": backend,
            "required_tables": sorted(Base.metadata.tables),
            "read_only": True,
        }
        started = time.monotonic()
        try:
            expected = sorted(ScriptDirectory(str(SCRIPT_LOCATION)).get_heads())
            with engine.connect() as connection:
                connection.execute(text("SELECT 1")).one()
                for table in Base.metadata.sorted_tables:
                    connection.execute(select(table).limit(0)).all()
                revisions = sorted(MigrationContext.configure(connection).get_current_heads())
            if not expected or revisions != expected:
                return {
                    **metadata,
                    "status": "unavailable",
                    "migration": {
                        "status": "mismatch",
                        "revisions": None,
                        "expected_heads": expected,
                    },
                    "detail": "Business database migration does not match the application",
                }
            return {
                **metadata,
                "status": "ok",
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
                "migration": {"status": "ok", "revisions": revisions, "expected_heads": expected},
            }
        except Exception:
            return {
                **metadata,
                "status": "unavailable",
                "latency_ms": None,
                "detail": "Business database probe failed",
            }

    def resources(self) -> dict[str, Any]:
        """Collect host resources; CPU has a bounded 100 ms measurement window."""
        result: dict[str, Any] = {"scope": "api_host"}
        try:
            # interval=None reports a meaningless first zero per worker thread.
            percent = psutil.cpu_percent(interval=0.1)
            if not math.isfinite(percent) or not 0 <= percent <= 100:
                raise ValueError("Invalid CPU measurement")
            result["cpu"] = {"status": "ok", "percent": percent, "sample_seconds": 0.1}
        except Exception:
            result["cpu"] = {**_unknown(), "percent": None, "sample_seconds": 0.1}
        try:
            memory = psutil.virtual_memory()
            result["memory"] = {
                "status": "ok",
                "total_bytes": memory.total,
                "available_bytes": memory.available,
                "used_bytes": memory.used,
                "percent": memory.percent,
            }
        except Exception:
            result["memory"] = _unknown()
        try:
            disk = shutil.disk_usage(self.files.root)
            result["disk"] = {
                "status": "ok",
                "scope": "upload_filesystem",
                "total_bytes": disk.total,
                "used_bytes": disk.used,
                "free_bytes": disk.free,
                "percent": round(disk.used / disk.total * 100, 2) if disk.total else None,
            }
        except Exception:
            result["disk"] = _unknown()
        try:
            with self.files.store.connection() as db:
                row = db.execute(
                    "SELECT COUNT(*), COALESCE(SUM(size),0) FROM api_file_objects WHERE deleted=0"
                ).fetchone()
            result["file_storage"] = {
                "status": "ok",
                "active_files": row[0],
                "active_bytes": row[1],
                "scope": "registered_artifacts",
                "includes_unregistered_or_temporary_files": False,
            }
        except Exception:
            result["file_storage"] = _unknown()
        result["status"] = (
            "ok"
            if all(
                result[name]["status"] == "ok" for name in ("cpu", "memory", "disk", "file_storage")
            )
            else "unknown"
        )
        return result

    def _sandbox_config(self) -> SandboxConfig:
        return SandboxConfig(
            backend="docker",
            docker_image=self.settings.MONITOR_SANDBOX_IMAGE,
            timeout_seconds=self.settings.MONITOR_SANDBOX_TIMEOUT_SECONDS,
        )

    def sandbox(self) -> dict[str, Any]:
        """Share one real Docker preflight among concurrent callers for a short TTL."""
        with self._sandbox_lock:
            now = time.monotonic()
            if (
                self._sandbox_result is not None
                and now - self._sandbox_checked_at < self.settings.MONITOR_PROBE_CACHE_SECONDS
            ):
                return {**self._sandbox_result, "cached": True}
            try:
                healthy, _detail = SandboxExecutor(self._sandbox_config()).health_check()
            except Exception:
                healthy = False
            result: dict[str, Any] = {
                "status": "ok" if healthy else "unavailable",
                "backend": "docker",
                "scope": "docker_execution_preflight",
                "cached": False,
                "cache_seconds": self.settings.MONITOR_PROBE_CACHE_SECONDS,
            }
            if not healthy:
                result["detail"] = "Docker sandbox preflight failed"
            self._sandbox_result = result
            self._sandbox_checked_at = time.monotonic()
            return dict(result)

    def redis(self) -> dict[str, Any]:
        return self.queue.read("redis")

    def workers(self) -> dict[str, Any]:
        return self.queue.read("workers")

    def close(self) -> None:
        self.queue.close()
        self.container_resources.close()

    def containers(self) -> dict[str, Any]:
        return self.container_resources.read()

    @staticmethod
    def cache_stats(cache: LLMResponseCache | None = None) -> dict[str, Any]:
        if cache is None:
            return {"status": "not_configured", "scope": "bound_cache_instance"}
        try:
            stats = cache.stats()
            safe: dict[str, Any] = {}
            for key in _CACHE_FIELDS:
                value = stats.get(key)
                if key == "enabled":
                    if not isinstance(value, bool):
                        raise ValueError("Invalid cache status")
                elif (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value < 0
                ):
                    raise ValueError("Invalid cache measurement")
                safe[key] = value
            return {
                "status": "ok",
                "scope": "bound_cache_instance",
                "counters_scope": "in_process_since_instance_creation",
                **safe,
            }
        except Exception:
            return {**_unknown(), "scope": "bound_cache_instance"}

    @staticmethod
    def strategies() -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "defaults": StrategyConfig(name=name).model_dump(
                    exclude={"system_prompt", "custom_params"}
                ),
            }
            for name in AlgorithmHarness.STRATEGY_MAP
        ]

    @staticmethod
    def providers() -> dict[str, Any]:
        """Expose an offline example catalog, never query paid provider endpoints."""
        supported = sorted(get_args(LLMConfig.model_fields["provider"].annotation))
        catalog: dict[str, set[str]] = {provider: set() for provider in supported}
        root = Path(__file__).resolve().parents[2]
        available = True
        for filename in _CATALOG_FILES:
            try:
                with (root / filename).open(encoding="utf-8") as source:
                    # Fixed example files only; never read a private runtime config.
                    config = json.loads(source.read(262145))
                llm = config.get("llm_config", {})
                provider, model = llm.get("provider"), llm.get("model")
                if provider in catalog and isinstance(model, str) and _MODEL_NAME.fullmatch(model):
                    catalog[provider].add(model)
            except (OSError, ValueError, TypeError, AttributeError):
                available = False
        return {
            "status": "ok" if available else "unknown",
            "scope": "offline_example_catalog",
            "live_provider_availability_checked": False,
            "providers": [
                {"provider": provider, "models": sorted(catalog[provider])}
                for provider in supported
            ],
        }

    def sandbox_config(self) -> dict[str, Any]:
        return self._sandbox_config().model_dump(
            include={
                "backend",
                "docker_image",
                "timeout_seconds",
                "memory_limit_mb",
                "max_output_bytes",
                "max_processes",
                "allowed_imports",
            }
        )
