"""Strict input models; secret values are never serialized in responses."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class ProfileUpdate(InputModel):
    username: str | None = Field(None, min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str | None = Field(
        None, min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    )


class RegisterInput(InputModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: SecretStr = Field(min_length=12, max_length=1024)


class LoginInput(InputModel):
    username: str = Field(min_length=1, max_length=254)
    password: SecretStr = Field(min_length=1, max_length=1024)


class RefreshInput(InputModel):
    refresh_token: SecretStr = Field(min_length=1, max_length=4096)


class PasswordChange(InputModel):
    current_password: SecretStr = Field(min_length=1, max_length=1024)
    new_password: SecretStr = Field(min_length=12, max_length=1024)


class KeyCreate(InputModel):
    provider: Literal["openai", "anthropic", "siliconflow"]
    key_name: str = Field(min_length=1, max_length=100)
    api_key: SecretStr = Field(min_length=1, max_length=4096)

    @field_validator("api_key")
    @classmethod
    def literal_key(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if (
            not raw.strip()
            or raw.lower().startswith("env:")
            or raw.startswith("${")
            or any(c in raw for c in "\r\n\x00")
        ):
            raise ValueError("A literal API key is required")
        return value


class KeyUpdate(InputModel):
    key_name: str | None = Field(None, min_length=1, max_length=100)
    api_key: SecretStr | None = Field(None, min_length=1, max_length=4096)

    @field_validator("api_key")
    @classmethod
    def literal_key(cls, value: SecretStr | None) -> SecretStr | None:
        return KeyCreate.literal_key(value) if value is not None else None
