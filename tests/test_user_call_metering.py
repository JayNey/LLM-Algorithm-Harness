"""Persistent per-user generation counts and UTC calendar boundaries."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from api.auth.store import AuthStore
from src.llm_client import LLMClient
from src.models import LLMConfig


def stamp(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc).timestamp()


def test_calendar_rollover_restart_and_owners(tmp_path, monkeypatch):
    path = tmp_path / "auth.db"
    store = AuthStore(path)
    now = [stamp("2026-12-31T23:59:59")]
    monkeypatch.setattr("api.auth.store.time.time", lambda: now[0])
    store.record_user_api_call("alice")
    store.record_user_api_call("alice")
    store.record_user_api_call("bob")
    counts = AuthStore(path).user_api_calls("alice")
    assert [counts[p]["used"] for p in ("daily_api_calls", "monthly_api_calls")] == [2, 2]
    assert counts["daily_api_calls"]["resets_at"] == "2027-01-01T00:00:00+00:00"
    assert counts["monthly_api_calls"]["period_start"] == "2026-12-01T00:00:00+00:00"
    assert store.user_api_calls("bob")["daily_api_calls"]["used"] == 1
    now[0] += 1
    assert store.user_api_calls("alice")["monthly_api_calls"]["used"] == 0
    store.record_user_api_call("alice")
    now[0] += 86400
    counts = store.user_api_calls("alice")
    assert counts["daily_api_calls"]["used"] == 0
    assert counts["monthly_api_calls"]["used"] == 1
    now[0] = stamp("2026-12-31T23:59:59")
    assert AuthStore(path).user_api_calls("alice")["daily_api_calls"]["used"] == 2


def test_concurrent_connections_do_not_lose_updates(tmp_path):
    path = tmp_path / "auth.db"
    stores = [AuthStore(path) for _ in range(4)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda n: stores[n % 4].record_user_api_call("alice"), range(40)))
    counts = AuthStore(path).user_api_calls("alice")
    assert counts["daily_api_calls"]["used"] == counts["monthly_api_calls"]["used"] == 40


def test_private_callback_retry_and_failures(tmp_path, monkeypatch):
    monkeypatch.setattr("api.monitoring.llm_metrics.record_call", Mock())
    store = AuthStore(tmp_path / "auth.db")
    client = LLMClient.__new__(LLMClient)
    client.config = LLMConfig(
        provider="openai",
        model="test",
        api_key="test",
        retry_max_attempts=2,
        retry_backoff_seconds=0,
    )
    client.config._record_api_attempt = lambda: store.record_user_api_call("alice")
    operation = Mock(side_effect=[ConnectionError("provider failed"), "response"])
    assert client._call_with_retry(operation) == "response"
    assert store.user_api_calls("alice")["daily_api_calls"]["used"] == 2
    assert "_record_api_attempt" not in client.config.model_dump()
    restored = LLMConfig.model_validate(
        {**client.config.model_dump(), "_record_api_attempt": Mock()}
    )
    assert restored._record_api_attempt is None
    client.config._record_api_attempt = Mock(side_effect=RuntimeError("db failed"))
    assert client._call_with_retry(lambda: "response") == "response"
    with pytest.raises(ValueError, match="original"):
        client._call_with_retry(Mock(side_effect=ValueError("original")))


@pytest.mark.parametrize(
    "instant,reset",
    [
        ("2024-02-29T23:59:59", "2024-03-01T00:00:00+00:00"),
        ("2026-04-30T23:59:59", "2026-05-01T00:00:00+00:00"),
    ],
)
def test_month_lengths(tmp_path, monkeypatch, instant, reset):
    store = AuthStore(tmp_path / "auth.db")
    monkeypatch.setattr("api.auth.store.time.time", lambda: stamp(instant))
    assert store.user_api_calls("alice")["monthly_api_calls"]["resets_at"] == reset


def test_transaction_rolls_back_both_periods(tmp_path):
    import sqlite3

    store = AuthStore(tmp_path / "auth.db")
    with store.connection() as db:
        db.execute("""CREATE TRIGGER reject_month BEFORE INSERT ON auth_user_api_calls
                    WHEN NEW.period='monthly_api_calls'
                    BEGIN SELECT RAISE(ABORT, 'test failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        store.record_user_api_call("alice")
    assert store.user_api_calls("alice")["daily_api_calls"]["used"] == 0


def test_worker_process_uses_same_database(tmp_path):
    import subprocess
    import sys

    path = tmp_path / "auth.db"
    store = AuthStore(path)
    code = "from pathlib import Path; from api.auth.store import AuthStore; import sys; AuthStore(Path(sys.argv[1])).record_user_api_call('alice')"
    result = subprocess.run(
        [sys.executable, "-c", code, str(path)], capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    assert store.user_api_calls("alice")["monthly_api_calls"]["used"] == 1


def test_user_count_independent_of_latency_clock(tmp_path, monkeypatch):
    store = AuthStore(tmp_path / "auth.db")
    client = LLMClient.__new__(LLMClient)
    client.config = LLMConfig(provider="openai", model="test", api_key="test")
    client.config._record_api_attempt = lambda: store.record_user_api_call("alice")
    monkeypatch.setattr("src.llm_client.time.perf_counter", Mock(side_effect=ValueError("clock")))
    assert client._call_with_retry(lambda: "response") == "response"
    assert store.user_api_calls("alice")["daily_api_calls"]["used"] == 1


def test_slow_failed_metering_does_not_suppress_provider_retry(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr("src.llm_client.time.monotonic", lambda: clock[0])
    monkeypatch.setattr("api.monitoring.llm_metrics.record_call", Mock())
    client = LLMClient.__new__(LLMClient)
    client.config = LLMConfig(
        provider="openai",
        model="test",
        api_key="test",
        retry_max_attempts=2,
        retry_max_elapsed_seconds=1,
        retry_backoff_seconds=0,
    )

    def slow_failed_meter():
        clock[0] += 2
        raise OSError("database locked")

    client.config._record_api_attempt = slow_failed_meter
    operation = Mock(side_effect=[ConnectionError("retryable"), "response"])
    assert client._call_with_retry(operation) == "response"
    assert operation.call_count == 2
