"""Real client/provider boundary and shared, payload-free collection."""

import os
import sqlite3
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from cryptography.fernet import Fernet

from api.auth.config import AuthSettings
from api.auth.store import AuthStore
from api.monitoring.store import MonitorStore
from src.llm_client import LLMClient
from src.models import LLMConfig


@pytest.fixture
def collected(tmp_path, monkeypatch):
    import api.monitoring.llm_metrics as metrics

    settings = AuthSettings(
        _env_file=None,
        SECRET_KEY="x" * 48,
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )
    monkeypatch.setattr(metrics, "AuthSettings", lambda: settings)
    metrics._configured_writer.cache_clear()
    store = MonitorStore(AuthStore(settings.AUTH_DATABASE_PATH))
    yield store, settings
    metrics._configured_writer.cache_clear()


def make_client(monkeypatch, provider="openai", **overrides):
    sdk = Mock()
    monkeypatch.setattr("src.llm_client.OpenAI", lambda **kwargs: sdk)
    monkeypatch.setattr("src.llm_client.Anthropic", lambda **kwargs: sdk)
    config = LLMConfig(
        **{
            "provider": provider,
            "model": "test-model",
            "api_key": "private-test-credential",
            "base_url": "http://localhost:1234/v1" if provider == "local" else None,
            "cache": {"enabled": False},
            "retry_max_attempts": 1,
            **overrides,
        }
    )
    client = LLMClient(config)
    operation = sdk.messages.create if provider == "anthropic" else sdk.chat.completions.create
    operation.return_value = (
        {
            "model": "test-model",
            "content": [{"type": "text", "text": "private-response"}],
            "usage": {"input_tokens": 2, "output_tokens": 3},
        }
        if provider == "anthropic"
        else {
            "model": "test-model",
            "choices": [{"message": {"content": "private-response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
        }
    )
    return client, sdk, operation


@pytest.mark.parametrize("provider", ["openai", "anthropic", "local", "siliconflow"])
@pytest.mark.parametrize("succeeded", [True, False])
def test_generation_outcomes_at_provider_boundary(collected, monkeypatch, provider, succeeded):
    store, settings = collected
    client, _, operation = make_client(monkeypatch, provider)
    if not succeeded:
        operation.side_effect = ValueError("private-test-credential private-error")
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr("src.llm_client.time.perf_counter", lambda: next(ticks))
    if succeeded:
        assert client.generate("private-prompt").text == "private-response"
    else:
        with pytest.raises(RuntimeError) as error:
            client.generate("private-prompt")
        assert "private-test-credential" not in str(error.value)
    operation.assert_called_once()
    stats = store.llm_stats()
    assert stats["total_calls"] == 1
    assert stats["successful_calls"] == int(succeeded)
    assert stats["failed_calls"] == int(not succeeded)
    assert stats["avg_latency_ms"] == 250.0
    with sqlite3.connect(settings.AUTH_DATABASE_PATH) as db:
        persisted = str(db.execute("SELECT * FROM api_monitor_meta").fetchall())
        assert all(
            value not in persisted
            for value in (
                "private-prompt",
                "private-response",
                "private-test-credential",
                "private-error",
            )
        )


def test_retries_count_attempts_and_exclude_backoff(collected, monkeypatch):
    store, _ = collected
    client, _, operation = make_client(monkeypatch, retry_max_attempts=2, retry_backoff_seconds=1)
    response = operation.return_value
    operation.side_effect = [TimeoutError("timed out"), response]
    ticks = iter([1.0, 1.1, 20.0, 20.3])
    monkeypatch.setattr("src.llm_client.time.perf_counter", lambda: next(ticks))
    sleep = Mock()
    monkeypatch.setattr("src.llm_client.time.sleep", sleep)
    assert client.generate("private-prompt").text == "private-response"
    stats = store.llm_stats()
    assert stats["total_calls"] == 2
    assert stats["successful_calls"] == stats["failed_calls"] == 1
    assert stats["avg_latency_ms"] == pytest.approx(200.0)
    sleep.assert_called_once_with(1)


def test_cache_and_model_list_do_not_count(collected, monkeypatch):
    store, _ = collected
    client, sdk, operation = make_client(monkeypatch, cache={"enabled": True})
    # Isolate disk cache while exercising the real generate() cache branch.
    saved = []
    client.cache = SimpleNamespace(
        get=lambda key: saved[0] if saved else None,
        set=lambda key, response: saved.append(response),
    )
    first = client.generate("private-prompt")
    assert client.generate("private-prompt") is first
    sdk.models.list.return_value = SimpleNamespace(data=[SimpleNamespace(id="test-model")])
    assert client.list_models() == ["test-model"]
    assert client.check_connection()["ok"] is True
    assert store.llm_stats()["total_calls"] == 1
    operation.assert_called_once()


@pytest.mark.parametrize("succeeded", [True, False])
@pytest.mark.parametrize("failure", ["writer", "clock_start", "clock_end", "settings"])
def test_collection_failures_preserve_result(collected, monkeypatch, succeeded, failure):
    import api.monitoring.llm_metrics as metrics

    client, _, operation = make_client(monkeypatch)
    original = ValueError("provider failed")
    if not succeeded:
        operation.side_effect = original
    if failure == "writer":
        monkeypatch.setattr(metrics, "record_call", Mock(side_effect=RuntimeError("sink failed")))
    elif failure == "settings":
        monkeypatch.setattr(metrics, "AuthSettings", Mock(side_effect=ValueError("no config")))
    else:
        side_effect = (
            [RuntimeError("clock failed")]
            if failure == "clock_start"
            else [1, RuntimeError("clock failed")]
        )
        monkeypatch.setattr("src.llm_client.time.perf_counter", Mock(side_effect=side_effect))
    if succeeded:
        assert client.generate("private-prompt").text == "private-response"
    else:
        with pytest.raises(RuntimeError, match="provider failed"):
            client.generate("private-prompt")
    operation.assert_called_once()


def test_worker_process_writes_visible_to_api_store(collected):
    store, settings = collected
    env = {
        **os.environ,
        "SECRET_KEY": settings.SECRET_KEY.get_secret_value(),
        "ENCRYPTION_KEY": settings.ENCRYPTION_KEY.get_secret_value(),
        "AUTH_DATABASE_PATH": str(settings.AUTH_DATABASE_PATH),
    }
    script = """
from src.llm_client import LLMClient
from src.models import LLMConfig
client = LLMClient.__new__(LLMClient)
client.config = LLMConfig(provider='openai', model='test', api_key='unused', retry_max_attempts=1)
assert client._call_with_retry(lambda: 'sdk-response') == 'sdk-response'
"""
    result = subprocess.run(
        [sys.executable, "-c", script], env=env, capture_output=True, timeout=30
    )
    assert result.returncode == 0
    assert store.llm_stats()["total_calls"] == 1
    assert store.llm_stats()["successful_calls"] == 1


def test_real_openai_sdk_transport_retry_is_observed(collected, monkeypatch):
    from openai import OpenAI

    store, _ = collected
    attempts = []

    def handle(request):
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(
                429, json={"error": {"message": "rate limit", "type": "rate_limit"}}
            )
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "sdk-response"},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5},
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handle)) as transport:
        sdk = OpenAI(api_key="private-test-credential", max_retries=0, http_client=transport)
        monkeypatch.setattr("src.llm_client.OpenAI", lambda **kwargs: sdk)
        client = LLMClient(
            LLMConfig(
                provider="openai",
                model="test-model",
                api_key="private-test-credential",
                cache={"enabled": False},
                retry_max_attempts=2,
                retry_backoff_seconds=0,
            )
        )
        assert client.generate("private-prompt").text == "sdk-response"
    assert len(attempts) == 2
    stats = store.llm_stats()
    assert stats["total_calls"] == 2
    assert stats["failed_calls"] == stats["successful_calls"] == 1


@pytest.mark.parametrize("warm", [True, False])
def test_locked_database_drops_sample_without_retrying_generation(collected, monkeypatch, warm):
    store, settings = collected
    client, _, operation = make_client(monkeypatch)
    if warm:
        client.generate("warm writer")
    with sqlite3.connect(settings.AUTH_DATABASE_PATH) as locked:
        locked.execute("BEGIN IMMEDIATE")
        assert client.generate("locked sample").text == "private-response"
        locked.rollback()
    assert store.llm_stats()["total_calls"] == int(warm)
    client.generate("recovered writer")
    assert operation.call_count == 2 + int(warm)
    assert store.llm_stats()["total_calls"] == 1 + int(warm)


def test_unconfigured_cli_still_generates(collected, monkeypatch):
    import api.monitoring.llm_metrics as metrics

    store, _ = collected
    for key in ("SECRET_KEY", "ENCRYPTION_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(metrics, "AuthSettings", lambda: AuthSettings(_env_file=None))
    client, _, operation = make_client(monkeypatch)
    assert client.generate("private-prompt").text == "private-response"
    operation.assert_called_once()
    assert store.llm_stats()["total_calls"] == 0
