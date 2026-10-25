"""Operator-controlled monitoring scope and retention; no client role claims."""

from uuid import UUID

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class MonitorSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    MONITOR_ADMIN_USER_IDS: list[UUID] = Field(default_factory=list)
    MONITOR_RETENTION_SECONDS: int = Field(604800, ge=60, le=2592000)
    MONITOR_MAX_ROWS: int = Field(10000, ge=100, le=100000)
    MONITOR_API_WINDOW_SECONDS: int = Field(60, ge=1, le=86400)
    MONITOR_PROBE_CACHE_SECONDS: int = Field(5, ge=0, le=300)
    MONITOR_QUEUE_PROBES_ENABLED: bool = False
    MONITOR_QUEUE_TIMEOUT_SECONDS: float = Field(3.0, ge=0.5, le=10, allow_inf_nan=False)
    MONITOR_QUEUE_CACHE_SECONDS: float = Field(5.0, ge=0, le=300, allow_inf_nan=False)
    MONITOR_CONTAINER_PROBES_ENABLED: bool = False
    MONITOR_CONTAINER_TIMEOUT_SECONDS: float = Field(3.0, ge=0.5, le=10, allow_inf_nan=False)
    MONITOR_CONTAINER_CACHE_SECONDS: float = Field(5.0, ge=0, le=300, allow_inf_nan=False)
    MONITOR_CONTAINER_MAX_ITEMS: int = Field(32, ge=1, le=64)
    MONITOR_SANDBOX_IMAGE: str = Field(
        "python:3.11-slim",
        min_length=1,
        max_length=255,
        pattern=r"^(?:[a-z0-9][a-z0-9.-]*(?::[0-9]+)?/)?[a-z0-9][a-z0-9._/-]*(?::[A-Za-z0-9._-]+)?(?:@sha256:[a-f0-9]{64})?$",
    )
    MONITOR_SANDBOX_TIMEOUT_SECONDS: int = Field(5, ge=1, le=30)

    def is_admin(self, user_id: str) -> bool:
        return any(str(value) == user_id for value in self.MONITOR_ADMIN_USER_IDS)


# Opt-in only: new settings must be reviewed before becoming externally visible.
# Keep arbitrary strings (including URLs, paths and identifiers) out of this view.
SYSTEM_CONFIG_FIELDS = {
    "api": (
        "MAX_CONCURRENT_TASKS",
        "MAX_CONCURRENT_EVALUATIONS_PER_USER",
        "TASK_TIMEOUT_SECONDS",
    ),
    "auth": (
        "ACCESS_TOKEN_EXPIRE_MINUTES",
        "REFRESH_TOKEN_EXPIRE_DAYS",
        "AUTH_RATE_LIMIT",
        "AUTH_RATE_WINDOW_SECONDS",
        "AUTH_PROTECTED_RATE_LIMIT",
        "USER_DAILY_API_CALL_LIMIT",
        "USER_MONTHLY_API_CALL_LIMIT",
    ),
    "files": (
        "FILE_UPLOAD_MAX_BYTES",
        "FILE_CONFIG_MAX_BYTES",
        "FILE_MAX_USER_BYTES",
        "FILE_TTL_SECONDS",
        "FILE_CLEANUP_INTERVAL_SECONDS",
        "FILE_UPLOAD_RATE_LIMIT",
        "FILE_MAX_CONCURRENT_TRANSFERS",
        "FILE_UPLOAD_TIMEOUT_SECONDS",
        "FILE_UPLOAD_IDLE_SECONDS",
        "FILE_MAX_CONCURRENT_IMPORTS",
        "FILE_MAX_ACTIVE_IMPORTS",
        "FILE_IMPORT_MAX_ITEMS",
        "FILE_IMPORT_TIMEOUT_SECONDS",
    ),
    "monitoring": (
        "MONITOR_RETENTION_SECONDS",
        "MONITOR_MAX_ROWS",
        "MONITOR_API_WINDOW_SECONDS",
        "MONITOR_PROBE_CACHE_SECONDS",
        "MONITOR_QUEUE_PROBES_ENABLED",
        "MONITOR_QUEUE_TIMEOUT_SECONDS",
        "MONITOR_QUEUE_CACHE_SECONDS",
        "MONITOR_CONTAINER_PROBES_ENABLED",
        "MONITOR_CONTAINER_TIMEOUT_SECONDS",
        "MONITOR_CONTAINER_CACHE_SECONDS",
        "MONITOR_CONTAINER_MAX_ITEMS",
        "MONITOR_SANDBOX_TIMEOUT_SECONDS",
    ),
}


def public_system_config(
    api: BaseSettings, auth: BaseSettings, files: BaseSettings, monitoring: MonitorSettings
) -> dict[str, object]:
    """Read only approved fields from the settings already used by this process."""
    sources = {"api": api, "auth": auth, "files": files, "monitoring": monitoring}
    return {
        "scope": "api_process",
        **{
            group: {field: getattr(sources[group], field) for field in fields}
            for group, fields in SYSTEM_CONFIG_FIELDS.items()
        },
    }
