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
        if redis_client is None:
            import redis as redis_sync

            redis_client = redis_sync.Redis.from_url(_redis_url())
        redis_client.publish(channel_for(task_id), json.dumps(payload))
        return True
    except Exception as exc:  # noqa: BLE001 - progress is best-effort
        logger.debug("progress_publish_failed", extra={"task_id": task_id, "error": str(exc)})
        return False


class ProgressStream:
    """Subscription source for progress channels (one stream per consumer)."""

    async def subscribe(self, channel: str) -> asyncio.Queue:
        """Start listening to ``channel``; returns a queue of decoded events."""
        raise NotImplementedError

    async def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        """Stop listening and release resources for this subscription."""
        raise NotImplementedError


class RedisProgressStream(ProgressStream):
    """Redis Pub/Sub backed stream (works across worker and API processes)."""

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url

    def _url(self) -> str:
        return self._redis_url or _redis_url()

    async def subscribe(self, channel: str) -> asyncio.Queue:
        import redis.asyncio as redis_async

        queue: asyncio.Queue = asyncio.Queue()
        client = redis_async.Redis.from_url(self._url())
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)

        async def pump() -> None:
            try:
                async for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    await queue.put(json.loads(message["data"]))
            except asyncio.CancelledError:
                pass
            finally:
                await pubsub.aclose()  # type: ignore[no-untyped-call]
                await client.aclose()

        queue.pump_task = asyncio.create_task(pump())  # type: ignore[attr-defined]
        return queue

    async def unsubscribe(self, channel: str, queue: asyncio.Queue) -> None:
        pump_task = getattr(queue, "pump_task", None)
        if pump_task is not None:
            pump_task.cancel()
            try:
                await pump_task
            except asyncio.CancelledError:
                pass
