"""Progress event plumbing between workers and WebSocket clients (issue #150).

Workers publish JSON events on the ``progress:{task_id}`` Redis channel;
the WebSocket endpoint forwards channel traffic to subscribed clients.
Publishing is best-effort: a Redis outage degrades progress streaming but
must never affect task execution.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

EVENT_CHANNEL_PREFIX = "progress:"


def channel_for(task_id: str) -> str:
    """Redis channel that carries progress events for ``task_id``."""
    return f"{EVENT_CHANNEL_PREFIX}{task_id}"


def _redis_url() -> str:
    from api.config import settings

    return settings.CELERY_BROKER_URL


_publisher: Any = None


def _publisher_client() -> Any:
    """Shared publish client with short timeouts (redis-py is thread-safe).

    Without tight timeouts a network black hole would stall every publish —
    twice per finished unit — for the OS-level TCP timeout.
    """
    global _publisher
    if _publisher is None:
        import redis as redis_sync

        _publisher = redis_sync.Redis.from_url(
            _redis_url(), socket_connect_timeout=1.0, socket_timeout=1.0
        )
    return _publisher


def publish_progress(
    task_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
    *,
    redis_client: Any = None,
) -> bool:
    """Publish one progress event for ``task_id``; return delivery success.

    Any Redis failure is logged and swallowed: a progress push must never
    break a running evaluation. ``redis_client`` lets tests inject a stub.
    """
    payload = {
        "type": event_type,
        "task_id": task_id,
        "data": data or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    try:
        client = redis_client if redis_client is not None else _publisher_client()
        client.publish(channel_for(task_id), json.dumps(payload))
        return True
    except Exception as exc:  # noqa: BLE001 - progress is best-effort
        logger.warning("progress_publish_failed", extra={"task_id": task_id, "error": str(exc)})
        return False


@dataclass
class Subscription:
    """One active channel subscription: decoded events land in ``queue``."""

    channel: str
    queue: asyncio.Queue[Any]
    pump_task: asyncio.Task | None = None


class ProgressStream:
    """Subscription source for progress channels (one stream per consumer)."""

    async def subscribe(self, channel: str) -> Subscription:
        """Start listening to ``channel``; returns a Subscription."""
        raise NotImplementedError

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Stop listening and release resources for this subscription."""
        raise NotImplementedError


class RedisProgressStream(ProgressStream):
    """Redis Pub/Sub backed stream (works across worker and API processes)."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url

    def _url(self) -> str:
        return self._redis_url or _redis_url()

    async def subscribe(self, channel: str) -> Subscription:
        import redis.asyncio as redis_async

        # Bounded queue: progress events are superseded by later ones, so a
        # stalled consumer drops the oldest instead of growing without bound.
        queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=200)
        client = redis_async.Redis.from_url(self._url())
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)

        async def pump() -> None:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        event = json.loads(message["data"])
                    except (ValueError, TypeError):
                        continue
                    if queue.full():
                        try:
                            queue.get_nowait()  # drop oldest
                        except asyncio.QueueEmpty:
                            pass
                    queue.put_nowait(event)
            except asyncio.CancelledError:
                pass
            finally:
                try:
                    await pubsub.aclose()  # type: ignore[no-untyped-call]
                    await client.aclose()
                except Exception:  # noqa: BLE001 - cleanup is best-effort
                    pass

        pump_task = asyncio.create_task(pump())
        return Subscription(channel=channel, queue=queue, pump_task=pump_task)

    async def unsubscribe(self, subscription: Subscription) -> None:
        """Cancel the pump; its finally block closes the redis resources."""
        if subscription.pump_task is not None:
            subscription.pump_task.cancel()
            try:
                await subscription.pump_task
            except asyncio.CancelledError:
                pass
