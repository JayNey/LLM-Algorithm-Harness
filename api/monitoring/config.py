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
