"""Real SQLite and offline statistics, with only Docker and failed host probes mocked."""

import json
import secrets
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import event, text

from api.auth.config import AuthSettings
from api.auth.service import AuthService
from api.files.config import FileSettings
from api.files.service import FileService
from api.models import EvaluationCreateRequest
from api.monitoring.config import MonitorSettings
from api.monitoring.probes import MonitorProbes
from api.services import EvaluationService
from src.cache import LLMResponseCache
from src.harness import AlgorithmHarness
from src.models import LLMResponse, StrategyConfig, TokenUsage


@pytest.fixture
def probes(tmp_path):
    auth = AuthService(
        AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=tmp_path / "private.sqlite3",
        )
    )
    files = FileService(auth, FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"))
    evaluations = EvaluationService(f"sqlite:///{tmp_path / 'business.sqlite3'}")
    try:
        yield MonitorProbes(auth, files, MonitorSettings(_env_file=None), evaluations)
    finally:
        evaluations.close()


def test_sqlite_probe_checks_real_connection_and_tables(probes):
    result = probes.database()
    assert result["status"] == "ok"
    assert result["authentication"] == {"status": "ok", "backend": "sqlite"}
    assert result["files"] == {"status": "ok", "backend": "sqlite"}
    assert result["business_database"]["status"] == "ok"
    assert (
        result["business_database"]["migration"]["revisions"]
        == result["business_database"]["migration"]["expected_heads"]
    )
    assert "experiments" in result["business_database"]["required_tables"]
    assert result["business_database"]["read_only"] is True
    with probes.files.store.connection() as db:
        db.execute("DROP TABLE api_file_objects")
    result = probes.database()
    assert result["status"] == "unavailable"
    assert result["authentication"]["status"] == "ok"
    assert result["files"]["status"] == "unavailable"
    assert str(probes.auth.store.path) not in json.dumps(result)


def test_business_probe_reuses_engine_without_task_recovery_or_writes(probes):
    run = probes.evaluations.create_evaluation(
        EvaluationCreateRequest(
            problem_ids=["p1"],
            strategy_names=["vanilla"],
            api_key_id="opaque-key",
            model="gpt-4o-mini",
        ),
        "operator",
    )
    statements = []

    def record(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement.split()[0].upper())

    event.listen(probes.evaluations.engine, "before_cursor_execute", record)
    try:
        with patch(
            "api.monitoring.probes.EvaluationService",
            side_effect=AssertionError("must not recreate service"),
        ):
            for _ in range(2):
                assert probes.database()["business_database"]["status"] == "ok"
        assert probes.evaluations.get_evaluation(run.evaluation_id, "operator").status == "pending"
        assert statements and set(statements) <= {"SELECT", "PRAGMA"}
    finally:
        event.remove(probes.evaluations.engine, "before_cursor_execute", record)


def test_business_probe_schema_and_migration_failure_never_echo_raw_details(probes):
    expected_revision = probes.database()["business_database"]["migration"]["revisions"][0]
    secret = "credential-private-invalid-revision"
    with probes.evaluations.engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num=:revision"), {"revision": secret}
        )
    response = probes.database()
    assert response["status"] == "unavailable"
    assert response["business_database"]["migration"]["status"] == "mismatch"
    assert secret not in json.dumps(response)
    with probes.evaluations.engine.begin() as connection:
        connection.execute(
            text("UPDATE alembic_version SET version_num=:revision"),
            {"revision": expected_revision},
        )
        connection.execute(text("DROP TABLE evaluation_results"))
    response = probes.database()
    assert response["business_database"]["status"] == "unavailable"
    assert response["authentication"]["status"] == "ok"


def test_business_connection_failure_is_explicit_and_safe(probes):
    secret = "postgresql://user:password@private-host/private-database"
    with patch.object(probes.evaluations.engine, "connect", side_effect=RuntimeError(secret)):
        response = probes.database()
    assert (
        response["status"] == "unavailable" and response["business_database"]["latency_ms"] is None
    )
    assert secret not in json.dumps(response)


def test_sqlite_connection_failure_remains_explicit_and_safe(probes, tmp_path):
    inaccessible = tmp_path / "private-connection-path"
    inaccessible.mkdir()
    probes.auth.store.path = inaccessible
    result = probes.database()
    assert result["status"] == "unavailable"
    assert result["authentication"]["status"] == "unavailable"
    assert result["files"]["status"] == "unavailable"
    assert str(inaccessible) not in json.dumps(result)


def test_resources_measure_actual_host_without_paths(probes):
    result = probes.resources()
    assert result["status"] == "ok"
    assert 0 <= result["cpu"]["percent"] <= 100
    assert result["cpu"]["sample_seconds"] == 0.1
    assert result["memory"]["total_bytes"] > 0
    assert result["memory"]["available_bytes"] >= 0
    assert result["disk"]["total_bytes"] > 0
    assert result["disk"]["free_bytes"] > 0
    assert result["file_storage"]["active_files"] == 0
    assert result["file_storage"]["active_bytes"] == 0
    assert str(probes.files.root) not in json.dumps(result)


def test_registered_storage_aggregates_live_files_and_excludes_deleted(probes):
    first = probes.files._persist(
        "operator", b"first private content", ".json", "one.json", "configs"
    )
    second = probes.files._persist(
        "operator", b"second private content", ".json", "two.json", "configs"
    )
    probes.files.store.mark_file_deleted(first["id"], "operator")
    storage = probes.resources()["file_storage"]
    assert storage["active_files"] == 1
    assert storage["active_bytes"] == second["size"]
    assert storage["includes_unregistered_or_temporary_files"] is False
    assert "private content" not in json.dumps(storage)


def test_psutil_failure_returns_unknown_without_fake_zero_or_exception(probes):
    secret = "private://user:password@host/private-path"
    with (
        patch("api.monitoring.probes.psutil.cpu_percent", side_effect=RuntimeError(secret)),
        patch("api.monitoring.probes.psutil.virtual_memory", side_effect=RuntimeError(secret)),
    ):
        result = probes.resources()
    assert result["status"] == "unknown"
    assert result["cpu"]["status"] == "unknown"
    assert result["cpu"]["percent"] is None
    assert result["memory"]["status"] == "unknown"
    assert "total_bytes" not in result["memory"]
    assert result["disk"]["status"] == "ok"
    assert secret not in json.dumps(result)


def test_invalid_cpu_sample_remains_unknown(probes):
    with patch("api.monitoring.probes.psutil.cpu_percent", return_value=float("nan")):
        result = probes.resources()
    assert result["cpu"]["status"] == "unknown"
    assert result["cpu"]["percent"] is None
    json.dumps(result, allow_nan=False)


def test_sandbox_uses_only_docker_and_safe_error_then_expires(probes):
    with patch("api.monitoring.probes.SandboxExecutor") as executor:
        executor.return_value.health_check.return_value = (False, "token=secret /private/path")
        failed = probes.sandbox()
        config = executor.call_args.args[0]
        assert config.backend == "docker"
        assert config.docker_image == probes.settings.MONITOR_SANDBOX_IMAGE
        assert failed["status"] == "unavailable"
        assert failed["cached"] is False
        assert "secret" not in json.dumps(failed)
        assert "/private/path" not in json.dumps(failed)
        assert probes.sandbox()["cached"] is True
        executor.assert_called_once()
        probes._sandbox_checked_at -= probes.settings.MONITOR_PROBE_CACHE_SECONDS + 1
        executor.return_value.health_check.return_value = (True, None)
        assert probes.sandbox()["status"] == "ok"
        assert executor.call_count == 2


def test_concurrent_sandbox_requests_share_single_preflight(probes):
    with patch("api.monitoring.probes.SandboxExecutor") as executor:
        executor.return_value.health_check.return_value = (True, None)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: probes.sandbox(), range(24)))
        assert all(result["status"] == "ok" for result in results)
        assert sum(not result["cached"] for result in results) == 1
        executor.assert_called_once()


def test_docker_exception_sanitized_and_cached(probes):
    with patch("api.monitoring.probes.SandboxExecutor", side_effect=RuntimeError("secret-path")):
        result = probes.sandbox()
        assert result["status"] == "unavailable"
        assert result["backend"] == "docker"
        assert "secret-path" not in json.dumps(result)
        assert probes.sandbox()["cached"] is True


def test_disabled_probe_cache_does_not_reuse_results(probes):
    probes.settings.MONITOR_PROBE_CACHE_SECONDS = 0
    with patch("api.monitoring.probes.SandboxExecutor") as executor:
        executor.return_value.health_check.return_value = (True, None)
        assert probes.sandbox()["cached"] is False
        assert probes.sandbox()["cached"] is False
        assert executor.call_count == 2


def test_future_dependencies_are_explicitly_unconfigured(probes):
    redis = probes.redis()
    assert redis["status"] == "not_checked" and redis["reason"] == "disabled"
    assert redis["infrastructure_available"] is True
    workers = probes.workers()
    assert workers["status"] == "not_checked" and workers["reason"] == "disabled"
    assert workers["infrastructure_available"] is True
    assert workers["evaluation_worker_implementation"] == "algorithm_harness"
    assert workers["real_evaluation_available"] is None
    assert probes.cache_stats() == {"status": "not_configured", "scope": "bound_cache_instance"}


def test_cache_reports_real_bound_instance_counters_without_entries_or_paths(tmp_path, probes):
    cache = LLMResponseCache(str(tmp_path / "cache"))
    response = LLMResponse(
        text="private response",
        model="local-test",
        usage=TokenUsage(prompt_tokens=5, completion_tokens=5, total_tokens=10),
    )
    cache.set("opaque-key", response)
    cache.get("opaque-key")
    cache.get("missing")
    result = probes.cache_stats(cache)
    assert result["status"] == "ok"
    assert result["hits"] == 1
    assert result["misses"] == 1
    assert result["hit_rate"] == 0.5
    assert result["total_entries"] == 1
    assert result["counters_scope"] == "in_process_since_instance_creation"
    assert "private response" not in json.dumps(result)
    assert "opaque-key" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)
    assert probes.cache_stats(LLMResponseCache(enabled=False))["enabled"] is False


def test_cache_has_only_public_fields_and_invalid_metrics_cannot_escape(tmp_path, probes):
    cache = LLMResponseCache(str(tmp_path / "cache"))
    assert set(probes.cache_stats(cache)) == {
        "status",
        "scope",
        "counters_scope",
        "enabled",
        "total_entries",
        "disk_usage_mb",
        "hit_rate",
        "hits",
        "misses",
        "api_calls_saved",
    }
    cache.hits = float("nan")
    result = probes.cache_stats(cache)
    assert result["status"] == "unknown"
    assert "hits" not in result
    json.dumps(result, allow_nan=False)


def test_strategy_directory_reuses_registry_and_schema_defaults(probes):
    result = probes.strategies()
    assert [item["name"] for item in result] == list(AlgorithmHarness.STRATEGY_MAP)
    for item in result:
        expected = StrategyConfig(name=item["name"])
        assert item["defaults"]["max_tokens"] == expected.max_tokens
        assert item["defaults"]["temperature"] == expected.temperature
        assert "system_prompt" not in item["defaults"]


def test_providers_catalog_is_offline_and_config_view_has_no_secrets(probes):
    # No LLM client or outbound transport is needed for offline configuration.
    result = probes.providers()
    assert result["status"] == "ok"
    assert result["scope"] == "offline_example_catalog"
    assert result["live_provider_availability_checked"] is False
    assert {item["provider"] for item in result["providers"]} == {
        "openai",
        "anthropic",
        "local",
        "siliconflow",
        "deepseek",
    }
    assert "gpt-3.5-turbo" in next(
        item["models"] for item in result["providers"] if item["provider"] == "openai"
    )
    encoded = json.dumps(result)
    assert "api_key" not in encoded and "base_url" not in encoded
    config = probes.sandbox_config()
    assert config["backend"] == "docker"
    assert config["timeout_seconds"] == probes.settings.MONITOR_SANDBOX_TIMEOUT_SECONDS
    assert "env" not in config and "path" not in json.dumps(config)


def test_worker_cache_real_client_shared_collection(tmp_path, probes, monkeypatch):
    from api.monitoring import llm_metrics
    from api.monitoring.store import MonitorStore
    from src.llm_client import LLMClient
    from src.models import CacheConfig, LLMConfig

    store = MonitorStore(probes.auth.store)
    monkeypatch.setattr(llm_metrics, "_configured_writer", lambda *args: store)
    monkeypatch.setattr(llm_metrics, "AuthSettings", lambda: probes.auth.settings)
    monkeypatch.chdir(tmp_path)
    config = LLMConfig(
        provider="openai", model="test", api_key="private-key", cache=CacheConfig(enabled=True)
    )
    response = LLMResponse(
        text="private-response",
        model="test",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    with (
        patch.object(LLMClient, "_initialize_client"),
        patch.object(LLMClient, "_call_openai", return_value=response) as sdk,
    ):
        client = LLMClient(config)
        assert client.generate("private-prompt") == response
        assert client.generate("private-prompt") == response
        assert sdk.call_count == 1
        data = probes.cache_stats()
        assert data["hits"] == data["misses"] == 1
        assert data["hit_rate"] == 0.5
        assert data["total_entries"] == 1
        assert data["disk_usage_mb"] > 0
        # Another instance shares the directory: capacity must not double.
        other = LLMClient(config)
        other.generate("private-prompt")
        data2 = probes.cache_stats()
        assert data2["hits"] == 2 and data2["misses"] == 1
        assert data2["total_entries"] == 1
        assert data2["disk_usage_mb"] == data["disk_usage_mb"]
        encoded = json.dumps(data2)
        for secret in ("private-key", "private-prompt", "private-response", str(tmp_path)):
            assert secret not in encoded
        with probes.auth.store.connection() as db:
            stored = str(
                db.execute("SELECT * FROM api_monitor_meta WHERE key LIKE 'cache:%'").fetchall()
            )
        assert "private-" not in stored and str(tmp_path) not in stored
        with patch.object(store, "record_cache_snapshot", side_effect=RuntimeError("private")):
            assert client.generate("private-prompt") == response


def test_worker_cache_snapshots_idempotent_bounded_and_stale(probes, monkeypatch):
    from api.monitoring.store import MonitorStore

    store = MonitorStore(probes.auth.store, retention_seconds=1000, max_rows=2)
    sample = dict(enabled=True, hits=2, misses=1, total_entries=3, disk_usage_mb=0.5)
    with patch("api.monitoring.store.time.time", return_value=1000):
        store.record_cache_snapshot("a" * 32, "b" * 64, sample)
        store.record_cache_snapshot("a" * 32, "b" * 64, sample)
        store.record_cache_snapshot("c" * 32, "b" * 64, sample)
        assert store.cache_stats()["hits"] == 4
        assert store.cache_stats()["total_entries"] == 3
    with patch("api.monitoring.store.time.time", return_value=1301):
        data = store.cache_stats()
        assert data["status"] == "partial" and data["disk_usage_mb"] is None
        assert data["hits"] == 4
    with patch("api.monitoring.store.time.time", return_value=1400):
        store.record_cache_snapshot(
            "d" * 32,
            "e" * 64,
            dict(enabled=False, hits=0, misses=0, total_entries=0, disk_usage_mb=0),
        )
        assert store.cache_stats()["observed_instances"] == 2
    with patch("api.monitoring.store.time.time", return_value=3000):
        assert store.cache_stats()["status"] == "not_configured"
    with pytest.raises(ValueError):
        store.record_cache_snapshot("x", "b" * 64, sample)


def test_worker_cache_cross_process_disabled_and_read_failure(tmp_path, probes):
    import subprocess
    import sys

    from api.monitoring.store import MonitorStore

    # A real separate process writes to the same DB that the API probe reads.
    script = """
import sys
from api.auth.store import AuthStore
from api.monitoring.store import MonitorStore
from pathlib import Path
store = MonitorStore(AuthStore(Path(sys.argv[1])))
store.record_cache_snapshot('a'*32, 'b'*64, dict(enabled=False, hits=0, misses=0, total_entries=0, disk_usage_mb=0))
"""
    subprocess.run(
        [sys.executable, "-c", script, str(probes.auth.store.path)],
        check=True,
        capture_output=True,
        timeout=30,
    )
    result = probes.cache_stats()
    assert result["status"] == "ok" and result["enabled"] is False
    assert result["hits"] == result["misses"] == 0
    assert result["hit_rate"] is None
    with patch.object(MonitorStore, "cache_stats", side_effect=RuntimeError(str(tmp_path))):
        data = probes.cache_stats()
        assert data["status"] == "unknown"
        assert str(tmp_path) not in json.dumps(data)


def test_worker_cache_expired_entry_is_miss(tmp_path, probes, monkeypatch):
    from api.monitoring import llm_metrics
    from api.monitoring.store import MonitorStore
    from src.llm_client import LLMClient
    from src.models import CacheConfig, LLMConfig

    store = MonitorStore(probes.auth.store)
    monkeypatch.setattr(llm_metrics, "_configured_writer", lambda *args: store)
    monkeypatch.setattr(llm_metrics, "AuthSettings", lambda: probes.auth.settings)
    monkeypatch.chdir(tmp_path)
    response = LLMResponse(
        text="answer",
        model="test",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
    )
    with (
        patch.object(LLMClient, "_initialize_client"),
        patch.object(LLMClient, "_call_openai", return_value=response) as sdk,
    ):
        client = LLMClient(
            LLMConfig(
                provider="openai", model="test", api_key="test-key", cache=CacheConfig(enabled=True)
            )
        )
        client.generate("prompt")
        client.cache.ttl_seconds = 0
        client.generate("prompt")
        assert sdk.call_count == 2
        result = probes.cache_stats()
        assert result["hits"] == 0 and result["misses"] == 2


def test_worker_cache_fork_does_not_duplicate_parent_counts(tmp_path, probes, monkeypatch):
    from api.monitoring import llm_metrics
    from api.monitoring.store import MonitorStore

    store = MonitorStore(probes.auth.store)
    monkeypatch.setattr(llm_metrics, "_configured_writer", lambda *args: store)
    monkeypatch.setattr(llm_metrics, "AuthSettings", lambda: probes.auth.settings)
    cache = LLMResponseCache(str(tmp_path / "cache"))
    cache.get("missing")
    llm_metrics.record_cache(cache)
    with patch.object(llm_metrics.os, "getpid", return_value=999999):
        cache.get("child-missing")
        llm_metrics.record_cache(cache)
    assert store.cache_stats()["misses"] == 2


def test_worker_cache_overall_rate_weights_cross_process_counts(probes):
    """Averaging worker rates (45%) or summing repeated snapshots must fail."""
    import subprocess
    import sys

    script = """
import sys
from pathlib import Path
from api.auth.store import AuthStore
from api.monitoring.store import MonitorStore

store = MonitorStore(AuthStore(Path(sys.argv[1])))
sample = dict(enabled=True, hits=int(sys.argv[3]), misses=int(sys.argv[4]),
              total_entries=3, disk_usage_mb=0.5)
for _ in range(2):
    store.record_cache_snapshot(sys.argv[2] * 32, 'b' * 64, sample)
"""
    for instance, hits, misses in (("a", "9", "1"), ("c", "0", "90")):
        subprocess.run(
            [sys.executable, "-c", script, str(probes.auth.store.path), instance, hits, misses],
            check=True,
            capture_output=True,
            timeout=30,
        )
    data = probes.cache_stats()
    assert data["hits"] == data["api_calls_saved"] == 9
    assert data["misses"] == 91
    assert data["hit_rate"] == pytest.approx(0.09)
    assert data["observed_instances"] == 2
    assert data["total_entries"] == 3
    assert data["disk_usage_mb"] == 0.5
    assert data["counters_scope"] == "retained_instance_lifetime_snapshots"
    assert data["cluster_complete"] is False


def test_worker_cache_updated_snapshot_and_expiry_change_rate(probes):
    """Replacing one snapshot must preserve other workers; expiry removes its counts."""
    from api.monitoring.store import MonitorStore

    store = MonitorStore(probes.auth.store, retention_seconds=1000)
    sample = dict(enabled=True, hits=9, misses=1, total_entries=1, disk_usage_mb=0.5)
    with patch("api.monitoring.store.time.time", return_value=1000):
        store.record_cache_snapshot("a" * 32, "b" * 64, sample)
    with patch("api.monitoring.store.time.time", return_value=1500):
        store.record_cache_snapshot("c" * 32, "d" * 64, {**sample, "hits": 0, "misses": 90})
        store.record_cache_snapshot("a" * 32, "b" * 64, {**sample, "hits": 19})
        data = store.cache_stats()
        assert data["hits"] == 19 and data["misses"] == 91
        assert data["hit_rate"] == pytest.approx(19 / 110)
    # Keep only worker c alive. Its lifetime misses remain, even if they
    # occurred before the retention window; retention applies to snapshots.
    with patch("api.monitoring.store.time.time", return_value=2400):
        store.record_cache_snapshot("c" * 32, "d" * 64, {**sample, "hits": 0, "misses": 90})
    with patch("api.monitoring.store.time.time", return_value=2501):
        data = store.cache_stats()
        assert data["observed_instances"] == 1
        assert data["hits"] == 0 and data["misses"] == 90
        assert data["hit_rate"] == 0.0


@pytest.mark.parametrize("enabled", [True, False])
def test_worker_cache_zero_queries_has_no_overall_rate(probes, enabled):
    from api.monitoring.store import MonitorStore

    MonitorStore(probes.auth.store).record_cache_snapshot(
        "a" * 32,
        "b" * 64,
        dict(enabled=enabled, hits=0, misses=0, total_entries=0, disk_usage_mb=0),
    )
    data = probes.cache_stats()
    assert data["enabled"] is enabled
    assert data["hits"] == data["misses"] == data["api_calls_saved"] == 0
    assert data["hit_rate"] is None
