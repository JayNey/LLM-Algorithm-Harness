"""Isolated Redis/Celery observation process; stdin carries private configuration."""

import contextlib
import hashlib
import json
import logging
import math
import os
import re
import sys
import time
from typing import Any
from urllib.parse import urlsplit

MAX_WORKERS = 128
MAX_OUTPUT_BYTES = 65536
COUNTERS = ("active", "reserved", "concurrency")


def unknown(kind: str, reason: str, status: str = "unknown") -> dict[str, Any]:
    result: dict[str, Any] = {"status": status, "reason": reason}
    if kind == "redis":
        result["latency_ms"] = None
    else:
        result.update(worker_count=None, workers=None, active=None, reserved=None, concurrency=None)
    return result


def counter(value: Any) -> int | None:
    return value if type(value) is int and 0 <= value <= 1000000 else None


def validated_result(kind: str, value: Any) -> dict[str, Any]:
    """Validate the subprocess protocol again at the API boundary."""
    if not isinstance(value, dict):
        raise ValueError("Invalid result")
    status, reason = value.get("status"), value.get("reason")
    if status in {"unknown", "unavailable", "unsupported", "not_configured"}:
        if reason not in {
            "invalid_reply",
            "no_replies",
            "probe_failed",
            "unsupported_transport",
            "invalid_configuration",
        }:
            raise ValueError("Invalid reason")
        return unknown(kind, reason, status)
    if status not in {"ok", "partial"}:
        raise ValueError("Invalid status")
    if kind == "redis":
        latency = value.get("latency_ms")
        if (
            status != "ok"
            or not isinstance(latency, (int, float))
            or isinstance(latency, bool)
            or not math.isfinite(latency)
            or not 0 <= latency <= 60000
        ):
            raise ValueError("Invalid latency")
        return {"status": "ok", "reason": "observed", "latency_ms": latency}
    rows = value.get("workers")
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_WORKERS:
        raise ValueError("Invalid workers")
    items = []
    identities: set[str] = set()
    partial = status == "partial"
    for row in rows:
        identity = row.get("worker_id") if isinstance(row, dict) else None
        if (
            not isinstance(identity, str)
            or not re.fullmatch(r"worker-[0-9a-f]{24}", identity)
            or identity in identities
        ):
            raise ValueError("Invalid worker identity")
        identities.add(identity)
        counts = {key: counter(row.get(key)) for key in COUNTERS}
        if counts["concurrency"] == 0:
            counts["concurrency"] = None
        complete = row.get("status") == "ok" and all(v is not None for v in counts.values())
        partial |= not complete
        items.append({"worker_id": identity, "status": "ok" if complete else "partial", **counts})
    return {
        "status": "partial" if partial else "ok",
        "reason": "incomplete_replies" if partial else "observed",
        "worker_count": len(items),
        "workers": items,
        **{key: sum(row[key] for row in items) if not partial else None for key in COUNTERS},
    }


def worker_snapshot(replies: Any) -> dict[str, Any]:
    """Whitelist counts, hash worker identities, and never imply a full census."""
    if not isinstance(replies, list):
        return unknown("workers", "invalid_reply")
    if not replies:
        return unknown("workers", "no_replies")
    workers: dict[str, dict[str, Any]] = {}
    partial = len(replies) > MAX_WORKERS
    for response in replies[:MAX_WORKERS]:
        if not isinstance(response, dict) or len(response) != 1:
            partial = True
            continue
        name, values = next(iter(response.items()))
        if not isinstance(name, str) or not 1 <= len(name) <= 256:
            partial = True
            continue
        identity = "worker-" + hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]
        if identity in workers:
            partial = True
            continue
        supported = (
            isinstance(values, dict)
            and type(values.get("version")) is int
            and values["version"] == 1
        )
        counts = {key: counter(values.get(key)) if supported else None for key in COUNTERS}
        if counts["concurrency"] == 0:
            counts["concurrency"] = None
        complete = supported and all(value is not None for value in counts.values())
        partial |= not complete
        workers[identity] = {
            "worker_id": identity,
            "status": "ok" if complete else "partial",
            **counts,
        }
    if not workers:
        return unknown("workers", "invalid_reply")
    totals = {
        key: sum(item[key] for item in workers.values()) if not partial else None
        for key in COUNTERS
    }
    return {
        "status": "partial" if partial else "ok",
        "reason": "incomplete_replies" if partial else "observed",
        "worker_count": len(workers),
        "workers": sorted(workers.values(), key=lambda item: item["worker_id"]),
        **totals,
    }


def probe(kind: str, broker_url: str, timeout: float) -> dict[str, Any]:
    if not isinstance(broker_url, str) or not broker_url or len(broker_url) > 8192:
        return unknown(kind, "invalid_configuration", "not_configured")
    if urlsplit(broker_url).scheme not in {"redis", "rediss"}:
        return unknown(kind, "unsupported_transport", "unsupported")
    if kind == "redis":
        import redis
        from redis.backoff import NoBackoff
        from redis.retry import Retry

        client = redis.Redis.from_url(broker_url)
        # URL query options override from_url kwargs. Clamp after parsing, before connecting.
        client.connection_pool.connection_kwargs.update(
            socket_connect_timeout=timeout,
            socket_timeout=timeout,
            retry=Retry(NoBackoff(), 0),
            retry_on_timeout=False,
            retry_on_error=[],
            health_check_interval=0,
        )
        started = time.monotonic()
        try:
            ok = client.ping()
            if ok is not True:
                return unknown(kind, "invalid_reply")
            return {
                "status": "ok",
                "reason": "observed",
                "latency_ms": round((time.monotonic() - started) * 1000, 3),
            }
        finally:
            client.close()
            client.connection_pool.disconnect()

    from celery import Celery

    app = Celery("monitoring_observer", broker=broker_url, set_as_current=False)
    app.conf.update(
        accept_content=["json"],
        task_serializer="json",
        broker_pool_limit=0,
        broker_connection_timeout=timeout,
        broker_connection_retry=False,
        broker_connection_retry_on_startup=False,
        broker_transport_options={
            "socket_connect_timeout": timeout,
            "socket_timeout": timeout,
            "retry_on_timeout": False,
            "max_retries": 0,
        },
    )
    try:
        with app.connection_for_read() as connection:
            connection.ensure_connection(max_retries=0)
            replies = app.control.broadcast(
                "monitoring_snapshot",
                reply=True,
                timeout=timeout,
                limit=MAX_WORKERS + 1,
                connection=connection,
                retry=False,
            )
        return worker_snapshot(replies)
    finally:
        app.close()


def main() -> None:
    logging.disable(logging.CRITICAL)
    kind = "workers"
    try:
        request = json.loads(sys.stdin.buffer.read(16385))
        kind = request["kind"]
        if kind not in {"redis", "workers"}:
            raise ValueError("Unknown probe")
        timeout = float(request["timeout"])
        if not 0 < timeout <= 5:
            raise ValueError("Invalid timeout")
        # Third-party diagnostics cannot become part of the stdout protocol.
        with (
            open(os.devnull, "w", encoding="utf-8") as discard,
            contextlib.redirect_stdout(discard),
        ):
            result = probe(kind, request["broker_url"], timeout)
    except Exception:
        result = unknown(kind, "probe_failed", "unavailable")
    encoded = json.dumps(result, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_OUTPUT_BYTES:
        encoded = json.dumps(unknown(kind, "invalid_reply"))
    sys.stdout.write(encoded)


if __name__ == "__main__":
    main()
