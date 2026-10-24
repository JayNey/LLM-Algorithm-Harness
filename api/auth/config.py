"""Required server secrets and bounded authentication settings."""

from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    SECRET_KEY: SecretStr
    ENCRYPTION_KEY: SecretStr
    AUTH_DATABASE_PATH: Path = Path("data/auth/auth.sqlite3")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(30, ge=1, le=1440)
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(7, ge=1, le=90)
    AUTH_RATE_LIMIT: int = Field(10, ge=1, le=1000)
    AUTH_RATE_WINDOW_SECONDS: int = Field(60, ge=1, le=3600)
    AUTH_PROTECTED_RATE_LIMIT: int = Field(120, ge=1, le=10000)
    USER_DAILY_API_CALL_LIMIT: int | None = Field(None, ge=0)
    USER_MONTHLY_API_CALL_LIMIT: int | None = Field(None, ge=0)

    @field_validator("USER_DAILY_API_CALL_LIMIT", "USER_MONTHLY_API_CALL_LIMIT", mode="before")
    @classmethod
    def empty_call_limit(cls, value: object) -> object:
        """Blank dotenv examples preserve the unlimited default."""
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator("SECRET_KEY")
    @classmethod
    def strong_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("SECRET_KEY must contain at least 32 bytes")
        return value

    @field_validator("ENCRYPTION_KEY")
    @classmethod
    def valid_encryption_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (ValueError, UnicodeError):
            raise ValueError("ENCRYPTION_KEY must be a Fernet key") from None
        return value
