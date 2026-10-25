"""Queue health boundaries, including real child termination without a broker."""

import json
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from api.monitoring.config import MonitorSettings
from api.monitoring.queue_health import QueueProbes
from api.monitoring.queue_probe import MAX_WORKERS, probe, validated_result, worker_snapshot
from src.tasks.monitoring import monitoring_snapshot
from tests.test_api_monitoring import api as api
from tests.test_api_monitoring import headers
from tests.test_api_monitoring_queue_compatibility import create_queue_task

BROKER = "redis://private-user:private-password@private-host:6379/9"
REAL_POPEN = subprocess.Popen


def settings(**changes):
    return MonitorSettings(_env_file=None, MONITOR_QUEUE_PROBES_ENABLED=True, **changes)


def child(monkeypatch, program):
    children = []
    started = threading.Event()

    def spawn(argv, **kwargs):
        assert argv == [sys.executable, "-m", "api.monitoring.queue_probe"]
        assert "private-password" not in repr(argv)
        assert kwargs["stderr"] == subprocess.DEVNULL
        process = REAL_POPEN([sys.executable, "-c", program], **kwargs)
        children.append(process)
        started.set()
        return process

    monkeypatch.setattr("api.monitoring.queue_health.subprocess.Popen", spawn)
    return children, started


def redis_program(prefix=""):
    return (
        prefix
        + "import sys,json; request=json.load(sys.stdin); print(json.dumps({'status':'ok','latency_ms':1,'secret':'private-password'}))"
    )


def test_disabled_and_closed_probes_do_not_spawn():
    queue = QueueProbes(MonitorSettings(_env_file=None), BROKER)
    with patch("api.monitoring.queue_health.subprocess.Popen", side_effect=AssertionError("spawn")):
        for kind in ("redis", "workers"):
            assert queue.read(kind)["status"] == "not_checked"
            assert queue.read(kind)["reason"] == "disabled"
        queue.close()
        assert queue.read("workers")["reason"] == "closed"
    with pytest.raises(ValueError):
        queue.read("arbitrary")


def test_real_child_protocol_cache_age_expiry_and_secret_filter(monkeypatch):
    children, _ = child(monkeypatch, redis_program())
    clock = [10.0]
    queue = QueueProbes(settings(), BROKER, clock=lambda: clock[0])
    first = queue.read("redis")
    assert first["status"] == "ok" and first["cached"] is False
    assert first["age_seconds"] == 0
    assert first["latency_ms"] == 1
    assert "private" not in json.dumps(first)
    clock[0] = 12
    again = queue.read("redis")
    assert again["cached"] is True and again["age_seconds"] == 2
    again["status"] = "tampered"
    assert queue.read("redis")["status"] == "ok"
    assert len(children) == 1 and children[0].poll() == 0
    clock[0] = 16
    assert queue.read("redis")["cached"] is False and len(children) == 2
    queue.close()


def test_real_hung_child_is_killed_and_reaped_within_total_budget(monkeypatch):
    children, _ = child(monkeypatch, "import time; time.sleep(60)")
    queue = QueueProbes(settings(MONITOR_QUEUE_TIMEOUT_SECONDS=0.5), BROKER)
    started = time.monotonic()
    result = queue.read("workers")
    assert time.monotonic() - started < 3
    assert result["status"] == "unknown" and result["reason"] == "timeout"
    assert result["active"] is None and result["worker_count"] is None
    assert children[0].poll() is not None
    assert children[0].stdout.closed and children[0].stdin.closed
    assert not queue._processes
    queue.close()


def test_concurrent_refresh_does_not_create_another_child_and_shutdown_cancels(monkeypatch):
    children, started = child(monkeypatch, "import time; time.sleep(60)")
    queue = QueueProbes(settings(MONITOR_QUEUE_TIMEOUT_SECONDS=10), BROKER)
    with ThreadPoolExecutor(max_workers=2) as executor:
        future = executor.submit(queue.read, "workers")
        assert started.wait(2)
        result = queue.read("workers")
        assert result["reason"] == "refresh_in_progress"
        assert len(children) == 1
        queue.close()
        assert future.result(timeout=3)["reason"] == "closed"
    assert children[0].poll() is not None
    assert not queue._processes
    queue.close()


@pytest.mark.parametrize(
    "program",
    [
        "print('not json private-password')",
        "import sys; sys.exit(1)",
        "print('x'*70000)",
        'print(\'{"status":"ok","latency_ms":true}\')',
        'print(\'{"status":"unknown","reason":"private-password"}\')',
    ],
)
def test_bad_child_output_cannot_become_health_or_secret_response(monkeypatch, program):
    children, _ = child(monkeypatch, program)
    queue = QueueProbes(settings(), BROKER)
    result = queue.read("redis")
    assert result["status"] == "unknown" and result["latency_ms"] is None
    assert "private" not in json.dumps(result)
    assert children[0].poll() is not None
    queue.close()


def test_process_start_failure_is_safe():
    queue = QueueProbes(settings(), BROKER)
    with patch("api.monitoring.queue_health.subprocess.Popen", side_effect=OSError(BROKER)):
        result = queue.read("redis")
    assert result["reason"] == "probe_start_failed"
    assert "private" not in json.dumps(result)
    queue.close()


def test_worker_command_counts_sets_without_inspecting_request_data():
    from celery.worker import state as worker_state

    active, waiting = Mock(), Mock()
    state = SimpleNamespace(
        tset=set, consumer=SimpleNamespace(pool=SimpleNamespace(limit=10, num_processes=4))
    )
    with (
        patch.object(worker_state, "active_requests", {active}),
        patch.object(worker_state, "reserved_requests", {active, waiting}),
    ):
        result = monitoring_snapshot(state)
    assert result == {"version": 1, "active": 1, "reserved": 1, "concurrency": 4}
    active.info.assert_not_called()
    waiting.info.assert_not_called()


def test_worker_command_registered_when_worker_imports_task_modules():
    from celery.worker.control import Panel

    from src.celery_app import celery_app

    celery_app.loader.import_default_modules()
    assert "src.tasks.monitoring" in celery_app.conf.include
    assert "monitoring_snapshot" in Panel.data
    assert Panel.meta["monitoring_snapshot"].type == "inspect"


def valid_reply(name="private-host", **counts):
    return {name: {"version": 1, "active": 1, "reserved": 2, "concurrency": 4, **counts}}


def test_worker_reply_projection_hides_host_names_and_extra_payloads():
    data = worker_snapshot(
        [
            valid_reply(args=["private-password"], broker=BROKER),
            valid_reply("second-private-host", active=0, reserved=0),
        ]
    )
    assert data["status"] == "ok" and data["worker_count"] == 2
    assert (data["active"], data["reserved"], data["concurrency"]) == (1, 2, 8)
    assert all(row["worker_id"].startswith("worker-") for row in data["workers"])
    assert "private" not in json.dumps(data)
    assert validated_result("workers", {**data, "secret": BROKER}) == data


@pytest.mark.parametrize("bad", [True, -1, 1.5, "1", 1000001, None, float("inf")])
def test_invalid_counts_are_partial_and_never_aggregated_as_zero(bad):
    data = worker_snapshot([valid_reply(active=bad)])
    assert data["status"] == "partial"
    assert data["active"] is None and data["reserved"] is None
    assert data["workers"][0]["active"] is None


def test_unknown_command_duplicate_and_reply_limit_are_incomplete():
    old = worker_snapshot([{"private-host": {"error": "private-password"}}])
    assert old["status"] == "partial" and old["worker_count"] == 1
    assert old["active"] is None and "private" not in json.dumps(old)
    duplicate = worker_snapshot([valid_reply(), valid_reply()])
    assert duplicate["status"] == "partial" and duplicate["worker_count"] == 1
    capped = worker_snapshot([valid_reply(str(n)) for n in range(MAX_WORKERS + 1)])
    assert capped["status"] == "partial" and capped["worker_count"] == MAX_WORKERS
    assert capped["active"] is None


@pytest.mark.parametrize("replies", [None, {}, [], [None], [{"": {}}], [{"a": {}, "b": {}}]])
def test_absent_or_malformed_replies_are_unknown(replies):
    data = worker_snapshot(replies)
    assert data["status"] == "unknown"
    assert data["worker_count"] is None and data["active"] is None


@pytest.mark.parametrize("url", ["amqp://private-password@host", "", None, "x" * 8193])
def test_unsupported_or_invalid_broker_does_not_open_connections(url):
    with patch("redis.Redis.from_url", side_effect=AssertionError("network")):
        result = probe("redis", url, 0.1)
    assert result["status"] in {"unsupported", "not_configured"}
    assert "private" not in json.dumps(result)


def test_redis_url_timeouts_are_clamped_after_parsing_and_connection_is_closed():
    client = Mock()
    client.connection_pool.connection_kwargs = {
        "socket_timeout": 999,
        "socket_connect_timeout": 999,
    }
    client.ping.return_value = True
    with patch("redis.Redis.from_url", return_value=client):
        result = probe("redis", BROKER + "?socket_timeout=999", 0.2)
    assert result["status"] == "ok"
    assert client.connection_pool.connection_kwargs["socket_timeout"] == 0.2
    assert client.connection_pool.connection_kwargs["socket_connect_timeout"] == 0.2
    client.close.assert_called_once()
    client.connection_pool.disconnect.assert_called_once()


@pytest.mark.parametrize(
    "field,value",
    [
        ("MONITOR_QUEUE_TIMEOUT_SECONDS", 0),
        ("MONITOR_QUEUE_TIMEOUT_SECONDS", 11),
        ("MONITOR_QUEUE_TIMEOUT_SECONDS", float("nan")),
        ("MONITOR_QUEUE_CACHE_SECONDS", -1),
        ("MONITOR_QUEUE_CACHE_SECONDS", float("inf")),
    ],
)
def test_probe_configuration_is_finite_and_bounded(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_enabled_queue_endpoints_keep_auth_and_public_liveness_boundaries(api):
    client, _, user, app, *_ = api
    app.state.monitor.settings.MONITOR_QUEUE_PROBES_ENABLED = True
    with patch(
        "api.monitoring.queue_health.subprocess.Popen", side_effect=AssertionError("network")
    ):
        assert client.get("/api/v1/health").status_code == 200
        for path in (
            "/health/redis",
            "/health/workers",
            "/system/workers",
            "/system/status",
            "/system/health",
        ):
            assert client.get("/api/v1" + path).status_code == 401
            assert client.get("/api/v1" + path, headers=headers(user)).status_code == 403


def test_http_health_and_status_share_one_worker_observation(api, monkeypatch):
    client, admin, _, app, *_ = api
    app.state.monitor.settings.MONITOR_QUEUE_PROBES_ENABLED = True
    app.state.monitor.settings.MONITOR_QUEUE_CACHE_SECONDS = 0
    task_id = create_queue_task(client, headers(admin))
    before = app.state.monitor.task_snapshot(task_source="async_task")
    result = worker_snapshot([valid_reply(active=0)])
    program = (
        "import sys,json; r=json.load(sys.stdin); "
        f"print(json.dumps({result!r} if r['kind']=='workers' else {{'status':'ok','latency_ms':1}}))"
    )
    children, _ = child(monkeypatch, program)
    response = client.get("/api/v1/system/status", headers=headers(admin))
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["workers"] == data["health"]["checks"]["workers"]
    assert data["workers"]["status"] == "ok" and data["workers"]["active"] == 0
    assert data["workers"]["cluster_complete"] is False
    assert data["real_evaluation_available"] is None
    assert data["async_task_counts"] == {"pending": 1}
    after = app.state.monitor.task_snapshot(task_source="async_task")
    assert after == before and after["items"][0]["task_id"] == task_id
    assert len(children) == 2  # One Redis and one worker probe, even with TTL=0.
    assert "private" not in response.text
    monkeypatch.setattr(app.state.monitor.probes, "sandbox", lambda: {"status": "ok"})
    health = client.get(
        "/api/v1/system/health?include_sandbox=true", headers=headers(admin)
    ).json()["data"]
    assert health["status"] == "healthy"
    assert health["pending_issues"] == []


def test_http_queue_failure_degrades_health_without_false_zero_counts(api, monkeypatch):
    client, admin, _, app, *_ = api
    app.state.monitor.settings.MONITOR_QUEUE_PROBES_ENABLED = True
    child(monkeypatch, "import sys; print('private-password',file=sys.stderr); sys.exit(1)")
    response = client.get("/api/v1/system/health", headers=headers(admin))
    data = response.json()["data"]
    assert data["status"] == "degraded"
    assert data["checks"]["workers"]["worker_count"] is None
    assert data["checks"]["redis"]["latency_ms"] is None
    assert "private-password" not in response.text


def queue_config(**changes):
    return {
        "queues": ["default", "evaluations"],
        "priority_steps": [0, 3, 6, 9],
        "sep": "\x06\x16",
        "global_keyprefix": "tenant:",
        **changes,
    }


def test_broker_waiting_counts_all_priority_buckets_without_consuming():
    client = MagicMock()
    client.connection_pool.connection_kwargs = {}
    client.ping.return_value = True
    pipe = client.pipeline.return_value.__enter__.return_value
    pipe.execute.return_value = [1, 0, 2, 0, 0, 2, 0, 0]
    with patch("redis.Redis.from_url", return_value=client):
        result = probe("redis", BROKER, 0.2, queue_config())
    assert result["broker_queue"] == {
        "status": "ok",
        "reason": "observed",
        "waiting": 5,
        "queues": [{"name": "default", "waiting": 3}, {"name": "evaluations", "waiting": 2}],
    }
    assert [call.args[0] for call in pipe.llen.call_args_list] == [
        "tenant:default",
        "tenant:default\x06\x163",
        "tenant:default\x06\x166",
        "tenant:default\x06\x169",
        "tenant:evaluations",
        "tenant:evaluations\x06\x163",
        "tenant:evaluations\x06\x166",
        "tenant:evaluations\x06\x169",
    ]
    assert client.pipeline.call_args.kwargs == {"transaction": False}
    assert not client.lpop.called and not client.rpop.called and not client.lrange.called


@pytest.mark.parametrize("sizes", [[0] * 8, [-1] * 8, [True] * 8, [0] * 7])
def test_empty_or_invalid_broker_counts_never_invent_zero(sizes):
    client = MagicMock()
    client.connection_pool.connection_kwargs = {}
    client.ping.return_value = True
    client.pipeline.return_value.__enter__.return_value.execute.return_value = sizes
    with patch("redis.Redis.from_url", return_value=client):
        result = probe("redis", BROKER, 0.2, queue_config())
    assert result["status"] == "ok"  # PING and waiting count have independent status.
    assert result["broker_queue"]["waiting"] == (0 if sizes == [0] * 8 else None)


def test_broker_count_failure_is_safe_and_ping_stays_observed():
    client = MagicMock()
    client.connection_pool.connection_kwargs = {}
    client.ping.return_value = True
    client.pipeline.side_effect = RuntimeError(BROKER)
    with patch("redis.Redis.from_url", return_value=client):
        result = probe("redis", BROKER, 0.2, queue_config())
    assert result["status"] == "ok"
    assert result["broker_queue"]["waiting"] is None
    assert "private" not in json.dumps(result)
    assert validated_result("redis", result) == result


@pytest.mark.parametrize(
    "changes",
    [
        {"priority_steps": []},
        {"queues": ["default", "default"]},
        {"priority_steps": [3, 0]},
        {"queues": []},
    ],
)
def test_invalid_queue_config_does_not_read_redis_keys(changes):
    client = MagicMock()
    client.connection_pool.connection_kwargs = {}
    client.ping.return_value = True
    with patch("redis.Redis.from_url", return_value=client):
        result = probe("redis", BROKER, 0.2, queue_config(**changes))
    assert result["broker_queue"]["waiting"] is None
    client.pipeline.assert_not_called()


def test_queue_disabled_and_protocol_cannot_forge_waiting_counts():
    queue = QueueProbes(MonitorSettings(_env_file=None), BROKER)
    assert queue.read("redis")["broker_queue"]["waiting"] is None
    result = {
        "status": "ok",
        "latency_ms": 1,
        "broker_queue": {
            "status": "ok",
            "reason": "observed",
            "waiting": 9,
            "queues": [{"name": "default", "waiting": 2}],
        },
    }
    assert validated_result("redis", result)["broker_queue"]["waiting"] is None
    queue.close()


def test_status_separates_broker_pending_and_reserved(api, monkeypatch):
    client, admin, _, app, *_ = api
    app.state.monitor.settings.MONITOR_QUEUE_PROBES_ENABLED = True
    create_queue_task(client, headers(admin))
    before = app.state.monitor.task_snapshot(task_source="async_task")
    program = (
        "import sys,json; r=json.load(sys.stdin); "
        f"print(json.dumps({worker_snapshot([valid_reply()])!r} if r['kind']=='workers' else "
        "{'status':'ok','latency_ms':1,'broker_queue':{'status':'ok','reason':'observed','waiting':5,'queues':[{'name':'default','waiting':5}]}}))"
    )
    child(monkeypatch, program)
    data = client.get("/api/v1/system/status", headers=headers(admin)).json()["data"]
    metrics = data["queue_metrics"]
    assert metrics["broker_queue"]["waiting"] == 5
    assert metrics["database_pending"]["count"] == 1
    assert metrics["worker_reserved"]["count"] == 2
    assert data["health"]["checks"]["redis"]["broker_queue"]["waiting"] == 5
    assert app.state.monitor.task_snapshot(task_source="async_task") == before
