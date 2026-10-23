"""Bound whole network observations, including DNS, retries and broker replies."""

import copy
import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from api.monitoring.capabilities import evaluation_capability
from api.monitoring.config import MonitorSettings
from api.monitoring.queue_probe import MAX_OUTPUT_BYTES, unknown, validated_result


class QueueProbes:
    def __init__(
        self,
        settings: MonitorSettings,
        broker_url: str,
        *,
        clock: Callable[[], float] = time.monotonic,
    ):
        from src.celery_app import celery_app

        options = celery_app.conf.broker_transport_options or {}
        self._queue_config = {
            "queues": sorted(celery_app.amqp.queues),
            "priority_steps": options.get("priority_steps", [0, 3, 6, 9]),
            "sep": options.get("sep", "\x06\x16"),
            "global_keyprefix": options.get("global_keyprefix", ""),
        }
        self.settings = settings
        self._broker_url = broker_url
        self._lock = threading.Lock()
        self._processes: dict[str, subprocess.Popen[bytes]] = {}
        self._cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._closed = False
        self._clock = clock

    def _base(self, kind: str) -> dict[str, Any]:
        return {
            "scope": "configured_celery_broker" if kind == "redis" else "responding_celery_workers",
            "infrastructure_available": True,
            "timeout_seconds": self.settings.MONITOR_QUEUE_TIMEOUT_SECONDS,
            **(
                {
                    "backend": "redis",
                    "queue_scope": "configured_business_queues",
                    "queue_excludes": ["worker_reserved", "active", "unacked", "worker_scheduled"],
                }
                if kind == "redis"
                else {
                    "cluster_complete": False,
                    "reserved_scope": "received_by_responding_workers_not_broker_queue_length",
                    **evaluation_capability(),
                }
            ),
        }

    def read(self, kind: str) -> dict[str, Any]:
        if kind not in {"redis", "workers"}:
            raise ValueError("Unknown queue probe")
        base = self._base(kind)
        with self._lock:
            if self._closed:
                return {**base, **unknown(kind, "closed"), "cached": False, "age_seconds": None}
            if not self.settings.MONITOR_QUEUE_PROBES_ENABLED:
                return {
                    **base,
                    **unknown(kind, "disabled", "not_checked"),
                    "cached": False,
                    "age_seconds": None,
                }
            now = self._clock()
            entry = self._cache.get(kind)
            if entry and now - entry[0] < self.settings.MONITOR_QUEUE_CACHE_SECONDS:
                return {
                    **base,
                    **copy.deepcopy(entry[1]),
                    "cached": True,
                    "age_seconds": round(max(0, now - entry[0]), 3),
                }
            if kind in self._processes:
                return {
                    **base,
                    **unknown(kind, "refresh_in_progress"),
                    "cached": False,
                    "age_seconds": None,
                }
            started = time.monotonic()
            try:
                process = subprocess.Popen(
                    [sys.executable, "-m", "api.monitoring.queue_probe"],
                    cwd=Path(__file__).resolve().parents[2],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                )
            except OSError:
                return {
                    **base,
                    **unknown(kind, "probe_start_failed"),
                    "cached": False,
                    "age_seconds": None,
                }
            self._processes[kind] = process
        timeout = self.settings.MONITOR_QUEUE_TIMEOUT_SECONDS
        payload = json.dumps(
            {
                "kind": kind,
                "broker_url": self._broker_url,
                "timeout": min(1.0, timeout / 3),
                "queue_config": self._queue_config if kind == "redis" else None,
            }
        ).encode("utf-8")
        try:
            output, _ = process.communicate(
                payload, timeout=max(0.01, timeout - (time.monotonic() - started))
            )
            if process.returncode != 0 or len(output) > MAX_OUTPUT_BYTES:
                raise ValueError("Invalid probe response")
            result = validated_result(kind, json.loads(output))
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()
            result = unknown(kind, "timeout")
        except Exception:
            if process.poll() is None:
                process.kill()
            process.communicate()
            result = unknown(kind, "probe_failed")
        finally:
            with self._lock:
                self._processes.pop(kind, None)
        with self._lock:
            if self._closed:
                return {**base, **unknown(kind, "closed"), "cached": False, "age_seconds": None}
            self._cache[kind] = (self._clock(), result)
        return {**base, **copy.deepcopy(result), "cached": False, "age_seconds": 0.0}

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._cache.clear()
            processes = list(self._processes.values())
            for process in processes:
                if process.poll() is None:
                    process.kill()
        for process in processes:
            process.wait(timeout=1)
