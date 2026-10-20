"""Read-only worker counts; never serialize Request.info(), arguments or broker stats."""

from typing import Any

from celery.worker import state as worker_state
from celery.worker.control import inspect_command


@inspect_command()  # type: ignore[untyped-decorator]
def monitoring_snapshot(state: Any, **kwargs: Any) -> dict[str, int | None]:
    """Count the same request sets as Celery inspect, without returning requests."""
    active = state.tset(worker_state.active_requests)
    reserved = state.tset(worker_state.reserved_requests) - active
    capacity = getattr(state.consumer.pool, "num_processes", None)
    return {
        "version": 1,
        "active": len(active),
        "reserved": len(reserved),
        "concurrency": capacity if type(capacity) is int and 0 < capacity <= 1000000 else None,
    }
