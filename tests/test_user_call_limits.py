"""Quota admission must block provider work and stay atomic across connections."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from pydantic import ValidationError

from api.auth.config import AuthSettings
from api.auth.service import AuthService
from api.auth.store import AuthStore
from api.middleware.errors import ApiError, ErrorCode
from src.llm_client import LLMClient


@pytest.fixture
def service(tmp_path):
    settings = AuthSettings(
        _env_file=None,
        SECRET_KEY="x" * 48,
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.db",
    )
    return AuthService(settings)


@pytest.mark.parametrize(
    "daily,monthly,period",
    [(1, None, "daily_api_calls"), (None, 1, "monthly_api_calls"), (0, 10, "daily_api_calls")],
)
def test_limits_block_without_changing_either_counter(service, daily, monthly, period):
    service.settings.USER_DAILY_API_CALL_LIMIT = daily
    service.settings.USER_MONTHLY_API_CALL_LIMIT = monthly
    if daily != 0:
        service.reserve_api_attempt("alice")
    before = service.store.user_api_calls("alice")
    with pytest.raises(ApiError) as error:
        service.reserve_api_attempt("alice")
    assert error.value.status_code == 429
    assert error.value.error_code == ErrorCode.QUOTA_EXCEEDED
    assert error.value.details["period"] == period
    assert int(error.value.headers["Retry-After"]) > 0
    assert service.store.user_api_calls("alice") == before
    if daily != 0:
        service.reserve_api_attempt("bob")


def test_concurrent_admission_and_restart(service):
    stores = [AuthStore(service.store.path) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda n: stores[n % 4].reserve_user_api_call("alice", 7, 20), range(30))
        )
    assert results.count(None) == 7
    counts = AuthStore(service.store.path).user_api_calls("alice")
    assert counts["daily_api_calls"]["used"] == counts["monthly_api_calls"]["used"] == 7


def test_rollover_does_not_bypass_monthly_limit(service, monkeypatch):
    now = [datetime(2026, 12, 30, 23, 59, 59, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr("api.auth.store.time.time", lambda: now[0])
    service.settings.USER_DAILY_API_CALL_LIMIT = 1
    service.settings.USER_MONTHLY_API_CALL_LIMIT = 1
    service.reserve_api_attempt("alice")
    now[0] += 86400
    with pytest.raises(ApiError) as error:
        service.reserve_api_attempt("alice")
    assert error.value.details["period"] == "monthly_api_calls"
    now[0] += 1
    service.reserve_api_attempt("alice")
    assert service.store.user_api_calls("alice")["monthly_api_calls"]["used"] == 1


def test_retry_stops_at_quota_before_provider(service, monkeypatch):
    service.settings.USER_DAILY_API_CALL_LIMIT = 1
    monkeypatch.setattr("api.monitoring.llm_metrics.record_call", lambda *args: None)
    from src.models import LLMConfig

    client = LLMClient.__new__(LLMClient)
    client.config = LLMConfig(
        provider="openai",
        model="test",
        api_key="test",
        retry_max_attempts=3,
        retry_backoff_seconds=0,
    )
    client.config._reserve_api_attempt = lambda: service.reserve_api_attempt("alice")
    attempts = []

    def provider():
        attempts.append(1)
        raise ConnectionError("offline")

    with pytest.raises(ApiError):
        client._call_with_retry(provider)
    assert len(attempts) == 1
    assert service.store.user_api_calls("alice")["daily_api_calls"]["used"] == 1
    assert "_reserve_api_attempt" not in client.config.model_dump()
    assert (
        LLMConfig.model_validate(
            {**client.config.model_dump(), "_reserve_api_attempt": lambda: None}
        )._reserve_api_attempt
        is None
    )


def test_storage_failure_is_closed(service, monkeypatch):
    import sqlite3

    def fail(*args):
        raise sqlite3.OperationalError("locked")

    monkeypatch.setattr(service.store, "reserve_user_api_call", fail)
    with pytest.raises(ApiError) as error:
        service.reserve_api_attempt("alice")
    assert error.value.status_code == 503


def test_negative_limit_rejected(service):
    with pytest.raises(ValidationError):
        AuthSettings(**{**service.settings.model_dump(), "USER_DAILY_API_CALL_LIMIT": -1})


def test_public_generation_preserves_admission_error(service, monkeypatch):
    from api.auth.models import KeyCreate, RegisterInput
    from src.models import CacheConfig

    user = service.register(
        RegisterInput(username="alice", email="alice@example.com", password="long-test-password")
    )["id"]
    key = service.add_key(
        user, KeyCreate(provider="openai", key_name="test", api_key="private-test-key")
    )["id"]
    service.settings.USER_DAILY_API_CALL_LIMIT = 0
    config = service.llm_config(key, user, "test")
    config.cache = CacheConfig(enabled=False)
    monkeypatch.setattr("src.llm_client.OpenAI", lambda **kwargs: object())
    client = LLMClient(config)
    with pytest.raises(ApiError) as error:
        client.generate("test prompt")
    assert error.value.error_code == ErrorCode.QUOTA_EXCEEDED
    assert service.store.user_api_calls(user)["daily_api_calls"]["used"] == 0


def test_reservation_rolls_back_both_periods(service):
    with service.store.connection() as db:
        db.execute("""CREATE TRIGGER reject_month BEFORE INSERT ON auth_user_api_calls
            WHEN NEW.period='monthly_api_calls'
            BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
    with pytest.raises(ApiError):
        service.reserve_api_attempt("alice")
    assert service.store.user_api_calls("alice")["daily_api_calls"]["used"] == 0


def test_processes_share_the_same_admission_limit(service):
    import subprocess
    import sys

    code = """from pathlib import Path
from api.auth.store import AuthStore
import sys
store = AuthStore(Path(sys.argv[1]))
print(sum(store.reserve_user_api_call('alice', 5, 10) is None for _ in range(10)))
"""
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(service.store.path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(3)
    ]
    admitted = []
    for worker in workers:
        out, err = worker.communicate(timeout=30)
        assert worker.returncode == 0, err.decode()
        admitted.append(int(out))
    assert sum(admitted) == 5
    assert service.store.user_api_calls("alice")["monthly_api_calls"]["used"] == 5


def test_slow_admission_does_not_suppress_provider_retry(service, monkeypatch):
    from src.models import LLMConfig

    clock = [0.0]
    monkeypatch.setattr("src.llm_client.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("api.monitoring.llm_metrics.record_call", lambda *args: None)
    service.settings.USER_DAILY_API_CALL_LIMIT = 2
    client = LLMClient.__new__(LLMClient)
    client.config = LLMConfig(
        provider="openai",
        model="test",
        api_key="test",
        retry_max_attempts=2,
        retry_max_elapsed_seconds=1,
        retry_backoff_seconds=0,
    )

    def slow_admission():
        clock[0] += 2
        service.reserve_api_attempt("alice")

    client.config._reserve_api_attempt = slow_admission
    attempts = []

    def provider():
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("retryable")
        return "response"

    assert client._call_with_retry(provider) == "response"
    assert len(attempts) == 2
    assert service.store.user_api_calls("alice")["daily_api_calls"]["used"] == 2


def test_empty_env_limits_keep_unlimited_default(service, monkeypatch):
    monkeypatch.setenv("USER_DAILY_API_CALL_LIMIT", "")
    monkeypatch.setenv("USER_MONTHLY_API_CALL_LIMIT", "")
    settings = AuthSettings(
        _env_file=None,
        SECRET_KEY="x" * 48,
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=service.store.path,
    )
    assert settings.USER_DAILY_API_CALL_LIMIT is None
    assert settings.USER_MONTHLY_API_CALL_LIMIT is None
