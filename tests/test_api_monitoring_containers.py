"""Container observations must remain scoped, bounded and honest about missing data."""

import hashlib
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from api.monitoring.config import MonitorSettings
from api.monitoring.containers import ContainerProbes, collect_containers
from src.utils import process_manager
from src.utils.process_manager import (
    BoundedRunResult,
    OutputLimitExceededError,
    ProcessTimeoutError,
)
from tests.test_api_monitoring import api as api
from tests.test_api_monitoring import headers

ID = "a" * 64
OTHER = "b" * 64
SECRET = "private-password-and-container-name"


def settings(**kwargs):
    return MonitorSettings(_env_file=None, MONITOR_CONTAINER_PROBES_ENABLED=True, **kwargs)


def raw(identity=ID, **changes):
    return json.dumps(
        {
            "id": identity,
            "cpu": "125.50%",
            "memory": "1.5MiB / 256MiB",
            "memory_percent": "0.59%",
            "pids": "2",
            "Name": SECRET,
            **changes,
        }
    )


def result(value, code=0):
    return BoundedRunResult(code, value.encode(), b"")


def snapshot(inventory=ID, stats=None, limit=32):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return result(inventory if command[1] == "ps" else raw() if stats is None else stats)

    probe = ContainerProbes(
        settings(MONITOR_CONTAINER_MAX_ITEMS=limit),
        collector=lambda timeout, count: collect_containers(timeout, count, runner=run),
    )
    return probe.read(), calls


def test_disabled_and_closed_never_collect():
    collect = Mock(side_effect=AssertionError("collect"))
    probe = ContainerProbes(MonitorSettings(_env_file=None), collector=collect)
    assert probe.read()["reason"] == "disabled"
    assert probe.read()["containers"] is None
    probe.close()
    assert probe.read()["reason"] == "closed"
    collect.assert_not_called()


def test_safe_metrics_only_and_fixed_readonly_commands():
    data, calls = snapshot()
    assert data["status"] == "ok" and data["listed_count"] == 1
    assert data["containers"][0] == {
        "container_id": "container-" + hashlib.sha256(ID.encode()).hexdigest()[:24],
        "status": "ok",
        "cpu_percent": 125.5,
        "memory_usage_bytes": 1572864,
        "memory_limit_bytes": 268435456,
        "memory_percent": 0.59,
        "pids": 2,
    }
    assert calls[0][0] == [
        "docker",
        "ps",
        "--no-trunc",
        "--filter",
        "label=io.llm-algorithm-harness.sandbox=v1",
        "--format",
        "{{.ID}}",
    ]
    assert calls[1][0][:4] == ["docker", "stats", "--no-stream", "--no-trunc"]
    assert calls[1][0][-1] == ID
    assert all(kw["max_output_bytes"] == 65536 for _, kw in calls)
    assert SECRET not in json.dumps(data) and ID not in json.dumps(data)


def test_empty_inventory_is_real_zero_without_stats_command():
    data, calls = snapshot(inventory="\n")
    assert data["status"] == "ok" and data["containers"] == []
    assert data["listed_count"] == data["sampled_count"] == 0
    assert len(calls) == 1


def test_sample_limit_and_vanished_measurement_are_partial():
    data, calls = snapshot(inventory=ID + "\n" + OTHER, limit=1)
    assert data["status"] == "partial" and data["truncated"] is True
    assert data["listed_count"] == 2 and data["sampled_count"] == 1
    assert OTHER not in calls[1][0]
    vanished, _ = snapshot(stats="")
    assert vanished["status"] == "partial"
    assert vanished["containers"][0]["cpu_percent"] is None
    assert vanished["containers"][0]["status"] == "unknown"


@pytest.mark.parametrize(
    "inventory,stats",
    [
        (ID + "\n" + ID, raw()),
        (SECRET, raw()),
        (ID, raw(OTHER)),
        (ID, raw() + "\n" + raw()),
        (ID, SECRET),
        (ID, "[]"),
    ],
)
def test_invalid_inventory_or_unselected_reply_is_not_a_measurement(inventory, stats):
    data, _ = snapshot(inventory, stats)
    assert data["status"] == "unknown" and data["reason"] == "invalid_reply"
    assert data["containers"] is None and data["listed_count"] is None
    assert SECRET not in json.dumps(data)


@pytest.mark.parametrize("value", ["NaN%", "Infinity%", "-1%", True, None, "101%"])
def test_missing_or_invalid_memory_percent_is_null(value):
    data, _ = snapshot(stats=raw(memory_percent=value))
    assert data["status"] == "partial"
    assert data["containers"][0]["memory_percent"] is None
    assert data["containers"][0]["cpu_percent"] == 125.5


def test_windows_missing_columns_and_stopped_zero_limit_are_not_faked():
    data, _ = snapshot(stats=raw(memory="38.21 MiB", memory_percent="--", pids="--"))
    row = data["containers"][0]
    assert data["status"] == "partial" and row["memory_usage_bytes"] > 0
    assert row["memory_limit_bytes"] is row["memory_percent"] is row["pids"] is None
    data, _ = snapshot(stats=raw(memory="0B / 0B"))
    assert data["status"] == "partial" and data["containers"][0]["memory_limit_bytes"] is None


def test_commands_share_remaining_time_budget():
    clock = [0.0]
    budgets = []

    def run(command, **kwargs):
        budgets.append(kwargs["timeout"])
        clock[0] += 2.5
        return result(ID if command[1] == "ps" else raw())

    collect_containers(3, 32, runner=run, clock=lambda: clock[0])
    assert budgets == [3, 0.5]


@pytest.mark.parametrize(
    "failure,reason,status",
    [
        (ProcessTimeoutError(SECRET), "timeout", "unknown"),
        (OutputLimitExceededError(SECRET), "output_limit", "unknown"),
        (FileNotFoundError(SECRET), "docker_unavailable", "unavailable"),
        (OSError(SECRET), "docker_unavailable", "unavailable"),
    ],
)
def test_failure_reasons_are_safe_and_negatively_cached(failure, reason, status):
    collect = Mock(side_effect=failure)
    probe = ContainerProbes(settings(), collector=collect)
    data = probe.read()
    assert (data["status"], data["reason"]) == (status, reason)
    assert data["containers"] is None and SECRET not in json.dumps(data)
    assert probe.read()["cached"] is True
    collect.assert_called_once()


def test_nonzero_exit_is_unavailable_without_stderr_leak():
    data = ContainerProbes(
        settings(),
        collector=lambda t, n: collect_containers(
            t, n, runner=lambda *a, **kw: result(SECRET, code=1)
        ),
    ).read()
    assert data["status"] == "unavailable" and SECRET not in json.dumps(data)


@pytest.mark.parametrize("stats", ["", raw()])
def test_stats_nonzero_after_successful_inventory_preserves_partial_readings(stats):
    def run(command, **kwargs):
        if command[1] == "ps":
            return result(ID + "\n" + OTHER)
        return BoundedRunResult(1, stats.encode(), SECRET.encode())

    data = ContainerProbes(
        settings(), collector=lambda t, n: collect_containers(t, n, runner=run)
    ).read()
    assert data["status"] == "partial" and data["reason"] == "stats_failed"
    assert data["listed_count"] == data["sampled_count"] == 2
    assert data["containers"][1]["status"] == "unknown"
    assert data["containers"][1]["cpu_percent"] is None
    assert data["containers"][0]["status"] == ("ok" if stats else "unknown")
    assert SECRET not in json.dumps(data)


def test_cache_age_expiry_and_defensive_copy():
    clock = [10.0]
    collect = Mock(return_value={"status": "ok", "reason": "observed", "containers": []})
    probe = ContainerProbes(settings(), collector=collect, clock=lambda: clock[0])
    first = probe.read()
    first["containers"].append(SECRET)
    clock[0] = 12
    assert probe.read()["age_seconds"] == 2
    assert probe.read()["containers"] == []
    assert collect.call_count == 1
    clock[0] = 16
    assert probe.read()["cached"] is False and collect.call_count == 2


def test_concurrent_refresh_and_close_do_not_publish_late_result():
    started, release = threading.Event(), threading.Event()

    def collect(timeout, limit):
        started.set()
        assert release.wait(2)
        return {"status": "ok", "reason": "observed", "containers": []}

    probe = ContainerProbes(settings(), collector=collect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(probe.read)
        assert started.wait(2)
        assert probe.read()["reason"] == "refresh_in_progress"
        closing = pool.submit(probe.close)
        deadline = time.monotonic() + 2
        while not probe._closed and time.monotonic() < deadline:
            time.sleep(0.005)
        assert probe.read()["reason"] == "closed"
        release.set()
        closing.result(timeout=2)
        assert future.result(timeout=2)["reason"] == "closed"


@pytest.mark.parametrize(
    "program,reason",
    [
        ("import time; time.sleep(60)", "timeout"),
        ("print('x'*200000)", "output_limit"),
    ],
)
def test_real_child_is_terminated_on_deadline_or_output_cap(monkeypatch, program, reason):
    real_spawn, real_run = process_manager.spawn, process_manager.run_bounded
    children = []

    def spawn(*args, **kwargs):
        process = real_spawn(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(process_manager, "spawn", spawn)

    def run(command, **kwargs):
        return real_run([sys.executable, "-c", program], **kwargs)

    probe = ContainerProbes(
        settings(MONITOR_CONTAINER_TIMEOUT_SECONDS=0.5),
        collector=lambda t, n: collect_containers(t, n, runner=run),
    )
    started = time.monotonic()
    assert probe.read()["reason"] == reason
    assert time.monotonic() - started < 5
    assert children and all(child.poll() is not None for child in children)


def test_public_and_unauthorized_requests_never_collect(api):
    client, admin, user, app, _, _, config = api
    config.MONITOR_CONTAINER_PROBES_ENABLED = True
    collect = Mock(side_effect=AssertionError("collect"))
    app.state.monitor.probes.container_resources._collector = collect
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/system/status").status_code == 401
    assert client.get("/api/v1/system/status", headers=headers(user)).status_code == 403
    collect.assert_not_called()
    collect.side_effect = None
    collect.return_value = {
        "status": "ok",
        "reason": "observed",
        "listed_count": 0,
        "sampled_count": 0,
        "truncated": False,
        "containers": [],
    }
    data = client.get("/api/v1/system/status", headers=headers(admin)).json()["data"]
    assert data["containers"]["containers"] == []
    collect.assert_called_once()


@pytest.mark.parametrize(
    "name,value",
    [
        ("MONITOR_CONTAINER_TIMEOUT_SECONDS", float("nan")),
        ("MONITOR_CONTAINER_TIMEOUT_SECONDS", float("inf")),
        ("MONITOR_CONTAINER_CACHE_SECONDS", float("nan")),
        ("MONITOR_CONTAINER_MAX_ITEMS", 0),
        ("MONITOR_CONTAINER_MAX_ITEMS", 65),
    ],
)
def test_configuration_bounds(name, value):
    with pytest.raises(ValidationError):
        settings(**{name: value})
