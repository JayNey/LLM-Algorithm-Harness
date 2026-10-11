"""Local file service limits, overridable through environment variables."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FileSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    UPLOAD_DIR: Path = Path("uploads")
    FILE_UPLOAD_MAX_BYTES: int = Field(100 * 1024 * 1024, ge=1)
    FILE_CONFIG_MAX_BYTES: int = Field(1024 * 1024, ge=1)
    FILE_MAX_USER_BYTES: int = Field(512 * 1024 * 1024, ge=1)
    FILE_TTL_SECONDS: int = Field(86400, ge=1)
    FILE_CLEANUP_INTERVAL_SECONDS: int = Field(300, ge=1)
    FILE_UPLOAD_RATE_LIMIT: int = Field(10, ge=1)
    FILE_MAX_CONCURRENT_TRANSFERS: int = Field(2, ge=1, le=16)
    FILE_UPLOAD_TIMEOUT_SECONDS: int = Field(120, ge=1)
    FILE_UPLOAD_IDLE_SECONDS: int = Field(15, ge=1)
    FILE_MAX_CONCURRENT_IMPORTS: int = Field(2, ge=1, le=16)
    FILE_MAX_ACTIVE_IMPORTS: int = Field(8, ge=1, le=100)
    FILE_IMPORT_MAX_ITEMS: int = Field(10000, ge=1, le=100000)
    FILE_IMPORT_TIMEOUT_SECONDS: int = Field(3600, ge=30)
