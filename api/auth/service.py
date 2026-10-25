"""Password, session and encrypted provider-key operations."""

import hashlib
import logging
import math
import sqlite3
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.fernet import Fernet, InvalidToken
from fastapi import HTTPException
from pydantic import SecretStr

from api.auth.config import AuthSettings
from api.auth.key_preview import masked_preview_from_secret
from api.auth.models import KeyCreate, KeyUpdate, PasswordChange, ProfileUpdate, RegisterInput
from api.auth.store import AuthStore
from api.middleware.errors import ApiError, ErrorCode
from src.llm_client import LLMAdmissionError, LLMClient
from src.models import CacheConfig, LLMConfig

logger = logging.getLogger(__name__)
ISSUER = "llm-algorithm-harness"
AUDIENCE = "harness-api"
PROVIDER_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "siliconflow": "https://api.siliconflow.cn/v1",
}
KEY_FIELDS = (
    "id",
    "provider",
    "key_name",
    "created_at",
    "last_used_at",
    "usage_count",
    "verification_count",
    "last_verified_at",
    "verified",
    "masked_preview",
)


def unauthorized(code: ErrorCode = ErrorCode.UNAUTHORIZED) -> HTTPException:
    return ApiError(
        "Invalid or expired credentials", code, 401, headers={"WWW-Authenticate": "Bearer"}
    )


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Principal:
    user_id: str
    session_id: str


class CallAdmissionError(ApiError, LLMAdmissionError):
    """A trusted admission failure, safe to propagate through generation."""


class AuthService:
    def __init__(self, settings: AuthSettings):
        self.settings = settings
        self.audit_sink: Callable[[str, str, str], None] | None = None
        self.store = AuthStore(settings.AUTH_DATABASE_PATH)
        self.passwords = PasswordHasher()
        self._dummy_hash = self.passwords.hash(uuid.uuid4().hex)
        self._fernet = Fernet(settings.ENCRYPTION_KEY.get_secret_value().encode("ascii"))
        self._secret = settings.SECRET_KEY.get_secret_value()

    def limit(self, bucket: str, limit: int | None = None) -> None:
        allowed, retry = self.store.allow(
            bucket, limit or self.settings.AUTH_RATE_LIMIT, self.settings.AUTH_RATE_WINDOW_SECONDS
        )
        if not allowed:
            raise HTTPException(429, "Too many requests", headers={"Retry-After": str(retry)})

    def audit(self, action: str, user_id: str, resource_id: str = "") -> None:
        logger.info("auth_audit action=%s user_id=%s resource_id=%s", action, user_id, resource_id)
        if self.audit_sink:
            try:
                self.audit_sink(action, user_id, resource_id)
            except Exception:
                logger.warning("monitor_audit_write_failed")

    def public_user(self, user_id: str) -> dict[str, Any]:
        user = self.store.user(user_id)
        if not user:
            raise unauthorized()
        return {key: user[key] for key in ("id", "username", "email", "created_at")}

    def register(self, request: RegisterInput) -> dict[str, Any]:
        user_id = str(uuid.uuid4())
        password_hash = self.passwords.hash(request.password.get_secret_value())
        try:
            self.store.add_user(user_id, request.username, request.email, password_hash)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username or email unavailable") from None
        self.audit("register", user_id)
        return self.public_user(user_id)

    def login(self, identity: str, password: str) -> dict[str, Any]:
        user = self.store.find_user(identity)
        try:
            self.passwords.verify(user["password_hash"] if user else self._dummy_hash, password)
        except (VerificationError, InvalidHashError):
            logger.info("auth_audit action=login_failed")
            raise unauthorized() from None
        if user is None:
            raise unauthorized()
        sid = str(uuid.uuid4())
        expires = int(time.time()) + self.settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400
        tokens = self._tokens(user["id"], sid, expires)
        self.store.add_session(sid, user["id"], digest(tokens["refresh_token"]), expires)
        self.audit("login", user["id"])
        return tokens

    def _tokens(self, user_id: str, sid: str, session_expires: int) -> dict[str, Any]:
        now = int(time.time())
        access_expires = min(now + self.settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60, session_expires)
        common = {
            "sub": user_id,
            "sid": sid,
            "iss": ISSUER,
            "aud": AUDIENCE,
            "iat": now,
            "nbf": now,
        }

        def encode(kind: str, expires: int) -> str:
            return jwt.encode(
                {**common, "type": kind, "exp": expires, "jti": str(uuid.uuid4())},
                self._secret,
                algorithm="HS256",
            )

        return {
            "access_token": encode("access", access_expires),
            "refresh_token": encode("refresh", session_expires),
            "token_type": "bearer",
            "expires_in": access_expires - now,
        }

    def decode(self, token: str, kind: str) -> dict[str, Any]:
        if len(token) > 4096:
            raise unauthorized(ErrorCode.INVALID_TOKEN)
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=ISSUER,
                audience=AUDIENCE,
                options={
                    "require": ["sub", "sid", "type", "jti", "exp", "iat", "nbf", "iss", "aud"]
                },
            )
            if claims["type"] != kind or any(
                not isinstance(claims[k], str) or not claims[k] for k in ["sub", "sid", "jti"]
            ):
                raise unauthorized(ErrorCode.INVALID_TOKEN)
            return claims
        except jwt.InvalidTokenError:
            raise unauthorized(ErrorCode.INVALID_TOKEN) from None

    def authenticate(self, token: str) -> Principal:
        claims = self.decode(token, "access")
        if not self.store.session(claims["sid"], claims["sub"]) or not self.store.user(
            claims["sub"]
        ):
            raise unauthorized(ErrorCode.INVALID_TOKEN)
        return Principal(claims["sub"], claims["sid"])

    def refresh(self, token: str) -> dict[str, Any]:
        claims = self.decode(token, "refresh")
        session = self.store.session(claims["sid"], claims["sub"])
        if not session or not self.store.user(claims["sub"]):
            raise unauthorized(ErrorCode.INVALID_TOKEN)
        tokens = self._tokens(claims["sub"], claims["sid"], session["expires_at"])
        if not self.store.rotate(
            claims["sid"], claims["sub"], digest(token), digest(tokens["refresh_token"])
        ):
            raise unauthorized(ErrorCode.INVALID_TOKEN)
        self.audit("refresh", claims["sub"])
        return tokens

    def logout(self, principal: Principal) -> None:
        self.store.revoke(principal.session_id, principal.user_id)
        self.audit("logout", principal.user_id)

    def change_password(self, principal: Principal, request: PasswordChange) -> None:
        user = self.store.user(principal.user_id)
        if user is None:
            raise unauthorized()
        current = request.current_password.get_secret_value()
        try:
            self.passwords.verify(user["password_hash"], current)
        except (VerificationError, InvalidHashError):
            self.audit("password_change_failed", principal.user_id)
            raise HTTPException(400, "当前密码不正确") from None
        self.store.update_password(
            principal.user_id, self.passwords.hash(request.new_password.get_secret_value())
        )
        self.audit("password_change", principal.user_id)

    def update_user(self, principal: Principal, request: ProfileUpdate) -> dict[str, Any]:
        try:
            self.store.update_user(principal.user_id, request.username, request.email)
        except sqlite3.IntegrityError:
            raise HTTPException(409, "Username or email unavailable") from None
        self.audit("profile_update", principal.user_id)
        return self.public_user(principal.user_id)

    def owned_key(self, key_id: str, user_id: str) -> dict[str, Any]:
        key = self.store.key(key_id, user_id)
        if not key:
            raise HTTPException(404, "API key not found")
        return key

    @staticmethod
    def key_metadata(key: dict[str, Any]) -> dict[str, Any]:
        return {name: key[name] for name in KEY_FIELDS}

    def add_key(self, user_id: str, request: KeyCreate) -> dict[str, Any]:
        key_id = str(uuid.uuid4())
        raw = request.api_key.get_secret_value()
        ciphertext = self._fernet.encrypt(raw.encode("utf-8")).decode("ascii")
        preview = masked_preview_from_secret(raw)
        self.store.add_key(key_id, user_id, request.provider, request.key_name, ciphertext, preview)
        self.audit("key_create", user_id, key_id)
        return self.key_metadata(self.owned_key(key_id, user_id))

    def update_key(self, key_id: str, user_id: str, request: KeyUpdate) -> dict[str, Any]:
        self.owned_key(key_id, user_id)
        ciphertext = None
        preview = None
        if request.api_key:
            raw = request.api_key.get_secret_value()
            ciphertext = self._fernet.encrypt(raw.encode("utf-8")).decode("ascii")
            preview = masked_preview_from_secret(raw)
        self.store.update_key(key_id, user_id, request.key_name, ciphertext, preview)
        self.audit("key_update", user_id, key_id)
        return self.key_metadata(self.owned_key(key_id, user_id))

    def delete_key(self, key_id: str, user_id: str) -> None:
        self.owned_key(key_id, user_id)
        self.store.delete_key(key_id, user_id)
        self.audit("key_delete", user_id, key_id)

    def llm_config(self, key_id: str, user_id: str, model: str) -> LLMConfig:
        """Internal worker hook; secret is never passed back through API schemas."""
        key = self.owned_key(key_id, user_id)
        try:
            raw = self._fernet.decrypt(key["ciphertext"].encode("ascii")).decode("utf-8")
            # Also validate persisted/imported records before the CLI client can
            # interpret environment-reference syntax.
            KeyCreate.literal_key(SecretStr(raw))
        except (InvalidToken, UnicodeError, ValueError):
            raise HTTPException(503, "Stored credential is unavailable") from None
        config = LLMConfig(
            provider=key["provider"],
            api_key=SecretStr(raw),
            model=model,
            timeout=5,
            retry_max_attempts=1,
            cache=CacheConfig(enabled=False),
        )

        if (
            self.settings.USER_DAILY_API_CALL_LIMIT is not None
            or self.settings.USER_MONTHLY_API_CALL_LIMIT is not None
        ):
            config._reserve_api_attempt = lambda: self.reserve_api_attempt(user_id)
        else:
            config._record_api_attempt = lambda: self.store.record_user_api_call(user_id)
        return config

    def reserve_api_attempt(self, user_id: str) -> None:
        try:
            denied = self.store.reserve_user_api_call(
                user_id,
                self.settings.USER_DAILY_API_CALL_LIMIT,
                self.settings.USER_MONTHLY_API_CALL_LIMIT,
            )
        except sqlite3.Error:
            raise CallAdmissionError(
                "Call quota storage unavailable", ErrorCode.SERVICE_UNAVAILABLE, 503
            ) from None
        if denied is not None:
            period, resets_at = denied
            raise CallAdmissionError(
                "User call quota exceeded",
                ErrorCode.QUOTA_EXCEEDED,
                429,
                details={"period": period, "resets_at": resets_at},
                headers={"Retry-After": str(max(1, math.ceil(resets_at - time.time())))},
            )

    def verify_key(self, key_id: str, user_id: str) -> dict[str, Any]:
        self.limit("verify:" + user_id)
        key = self.owned_key(key_id, user_id)
        client = None
        ok = False
        try:
            client = LLMClient(self.llm_config(key_id, user_id, "connection-check"))
            # list_models() does not forward LLMConfig.timeout. Configure the
            # SDK explicitly, including its URL (SDKs may read *_BASE_URL env).
            client.client = client.client.with_options(
                timeout=5.0, max_retries=0, base_url=PROVIDER_URLS[key["provider"]]
            )
            ok = client.check_connection().get("ok") is True
        except Exception:
            # SDK exception messages may contain credentials; never log them.
            pass
        finally:
            if client is not None:
                try:
                    client.client.close()
                except Exception:
                    pass
        self.store.record_verification(key_id, user_id, key["ciphertext"], ok)
        self.audit("key_verify_success" if ok else "key_verify_failed", user_id, key_id)
        return {
            "ok": ok,
            "provider": key["provider"],
            "message": "Connection verified" if ok else "Provider connection check failed",
        }
