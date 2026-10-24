"""Bounded, read-only observations of labeled sandboxes in this API's Docker context."""

import copy
import hashlib
import json
import math
import re
import threading
import time
from collections.abc import Callable
from typing import Any

from api.monitoring.config import MonitorSettings
from src.sandbox_executor import SANDBOX_CONTAINER_LABEL
from src.utils.process_manager import (
    BoundedRunResult,
    OutputLimitExceededError,
    ProcessTimeoutError,
    run_bounded,
)

MAX_OUTPUT_BYTES = 65536
CLEANUP_GRACE_SECONDS = 12
STATS_FORMAT = (
    '{"id":{{json .ID}},"cpu":{{json .CPUPerc}},"memory":{{json .MemUsage}},'
    '"memory_percent":{{json .MemPerc}},"pids":{{json .PIDs}}}'
)
_UNITS = {
    "B": 1,
    "kB": 1000,
    "MB": 1000**2,
    "GB": 1000**3,
    "TB": 1000**4,
    "KiB": 1024,
    "MiB": 1024**2,
    "GiB": 1024**3,
    "TiB": 1024**4,
}
_METRICS = ("cpu_percent", "memory_usage_bytes", "memory_limit_bytes", "memory_percent", "pids")


def _empty(reason: str, status: str = "unknown") -> dict[str, Any]:
    return {
        "status": status,
        "reason": reason,
        "listed_count": None,
        "sampled_count": None,
        "truncated": None,
        "containers": None,
    }


def _percent(value: Any, maximum: float) -> float | None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?%", value):
        return None
    number = float(value[:-1])
    return number if math.isfinite(number) and 0 <= number <= maximum else None


def _bytes(value: str) -> int | None:
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-z]+)\s*", value)
    if not match or match[2] not in _UNITS:
        return None
    number = float(match[1]) * _UNITS[match[2]]
    return int(number) if math.isfinite(number) and 0 <= number <= 2**63 - 1 else None


def _row(identity: str, raw: dict[str, Any] | None) -> dict[str, Any]:
    row: dict[str, Any] = {
        "container_id": "container-" + hashlib.sha256(identity.encode()).hexdigest()[:24],
        "status": "unknown",
        **dict.fromkeys(_METRICS),
    }
    if raw is None:
        return row
    memory = raw.get("memory")
    parts = memory.split("/") if isinstance(memory, str) else []
    used = _bytes(parts[0]) if parts else None
    limit = _bytes(parts[1]) if len(parts) == 2 else None
    pids = raw.get("pids")
    count = int(pids) if isinstance(pids, str) and re.fullmatch(r"[0-9]{1,10}", pids) else None
    row.update(
        cpu_percent=_percent(raw.get("cpu"), 1000000),
        memory_usage_bytes=used,
        memory_limit_bytes=limit if limit else None,
        memory_percent=_percent(raw.get("memory_percent"), 100),
        pids=count,
    )
    row["status"] = "ok" if all(row[key] is not None for key in _METRICS) else "partial"
    return row


def collect_containers(
    timeout: float,
    limit: int,
    *,
    runner: Callable[..., BoundedRunResult] | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> dict[str, Any]:
    """Read only fixed ps/stats commands. Errors never carry raw output to the API."""
    runner = runner or run_bounded
    deadline = clock() + timeout

    def run(command: list[str], *, allow_nonzero: bool = False) -> tuple[str, bool]:
        remaining = deadline - clock()
        if remaining <= 0:
            raise ProcessTimeoutError("Container observation timed out")
        result = runner(command, timeout=remaining, max_output_bytes=MAX_OUTPUT_BYTES)
        if result.returncode != 0 and not allow_nonzero:
            raise OSError("Docker observation unavailable")
        return result.stdout.decode("utf-8"), result.returncode != 0

    inventory, _ = run(
        [
            "docker",
            "ps",
            "--no-trunc",
            "--filter",
            "label=" + SANDBOX_CONTAINER_LABEL,
            "--format",
            "{{.ID}}",
        ]
    )
    identities = [line.strip() for line in inventory.splitlines() if line.strip()]
    if any(not re.fullmatch(r"[0-9a-f]{64}", identity) for identity in identities) or len(
        set(identities)
    ) != len(identities):
        raise ValueError("Invalid inventory")
    selected = identities[:limit]
    readings: dict[str, dict[str, Any]] = {}
    stats_failed = False
    if selected:
        # A --rm sandbox may finish after ps; stats can still emit other valid rows.
        output, stats_failed = run(
            ["docker", "stats", "--no-stream", "--no-trunc", "--format", STATS_FORMAT, *selected],
            allow_nonzero=True,
        )
        for line in output.splitlines():
            if not line.strip():
                continue
            value = json.loads(line)
            identity = value.get("id") if isinstance(value, dict) else None
            if not isinstance(identity, str) or identity not in selected or identity in readings:
                raise ValueError("Invalid reading")
            readings[identity] = value
    rows = [_row(identity, readings.get(identity)) for identity in selected]
    truncated = len(identities) > limit
    partial = truncated or stats_failed or any(row["status"] != "ok" for row in rows)
    return {
        "status": "partial" if partial else "ok",
        "reason": (
            "sample_limit"
            if truncated
            else (
                "stats_failed"
                if stats_failed
                else "partial_measurements" if partial else "observed"
            )
        ),
        "listed_count": len(identities),
        "sampled_count": len(selected),
        "truncated": truncated,
        "containers": rows,
    }


class ContainerProbes:
    def __init__(
        self,
        settings: MonitorSettings,
        *,
        collector: Callable[[float, int], dict[str, Any]] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.settings = settings
        self._collector = collector or collect_containers
        self._clock = clock
        self._lock = threading.Lock()
        self._done = threading.Event()
        self._done.set()
        self._running = False
        self._closed = False
        self._active_budget = settings.MONITOR_CONTAINER_TIMEOUT_SECONDS
        self._cache: tuple[float, tuple[float, int], dict[str, Any]] | None = None

    def _wrap(
        self, result: dict[str, Any], *, cached: bool = False, age: float | None = None
    ) -> dict[str, Any]:
        return {
            "scope": "api_process_docker_context_labeled_running_sandboxes",
            "selector": SANDBOX_CONTAINER_LABEL,
            "cluster_complete": False,
            "snapshot_atomic": False,
            "metrics_source": "docker_cli_rounded_stats",
            "timeout_seconds": self.settings.MONITOR_CONTAINER_TIMEOUT_SECONDS,
            "sample_limit": self.settings.MONITOR_CONTAINER_MAX_ITEMS,
            "cached": cached,
            "age_seconds": age,
            **copy.deepcopy(result),
        }

    def read(self) -> dict[str, Any]:
        with self._lock:
            if self._closed:
                return self._wrap(_empty("closed"))
            if not self.settings.MONITOR_CONTAINER_PROBES_ENABLED:
                return self._wrap(_empty("disabled", "not_configured"))
            key = (
                self.settings.MONITOR_CONTAINER_TIMEOUT_SECONDS,
                self.settings.MONITOR_CONTAINER_MAX_ITEMS,
            )
            now = self._clock()
            if (
                self._cache
                and self._cache[1] == key
                and now - self._cache[0] < self.settings.MONITOR_CONTAINER_CACHE_SECONDS
            ):
                return self._wrap(
                    self._cache[2], cached=True, age=round(max(0, now - self._cache[0]), 3)
                )
            if self._running:
                return self._wrap(_empty("refresh_in_progress"))
            self._running = True
            self._active_budget = key[0]
            self._done.clear()
        try:
            try:
                result = self._collector(*key)
            except ProcessTimeoutError:
                result = _empty("timeout")
            except OutputLimitExceededError:
                result = _empty("output_limit")
            except OSError:
                result = _empty("docker_unavailable", "unavailable")
            except ValueError:
                result = _empty("invalid_reply")
            except Exception:
                result = _empty("probe_failed")
            with self._lock:
                if self._closed:
                    return self._wrap(_empty("closed"))
                self._cache = (self._clock(), key, copy.deepcopy(result))
                return self._wrap(result, age=0.0)
        finally:
            with self._lock:
                self._running = False
                self._done.set()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cache = None
            budget = self._active_budget
        self._done.wait(timeout=budget + CLEANUP_GRACE_SECONDS)
