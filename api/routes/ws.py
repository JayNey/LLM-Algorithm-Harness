"""WebSocket endpoint for live evaluation progress (issue #150)."""

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth.cookies import ACCESS_COOKIE
from api.progress import Subscription, channel_for

router = APIRouter(prefix="/api/v1")

CLOSE_INVALID_TOKEN = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_INTERNAL = 1011


@router.websocket("/ws/progress")
async def ws_progress(websocket: WebSocket, token: str = "") -> None:
    """Live progress channel.

    Client frames: ``{"action": "subscribe", "task_id": ...}``,
    ``{"action": "unsubscribe", "task_id": ...}``, ``{"action": "ping"}``.
    Server frames carry ``type``: ``connected``/``task.snapshot``/worker
    events (``task.started``/``task.progress``/``problem.completed``/
    ``task.completed``/...) /``subscribed``/``unsubscribed``/``pong``.
    """
    app = websocket.app
    auth = app.state.auth
    evaluations = app.state.evaluations
    stream = app.state.progress_stream

    await websocket.accept()
    try:
        principal = auth.authenticate(token or websocket.cookies.get(ACCESS_COOKIE, ""))
    except Exception:
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="invalid token")
        return

    await websocket.send_json({"type": "connected", "user_id": principal.user_id})

    # task_id -> (subscription, forwarder task)
    listeners: dict[str, tuple[Subscription, asyncio.Task]] = {}

    async def forward(task_id: str, queue: asyncio.Queue) -> None:
        try:
            while True:
                event = await queue.get()
                try:
                    await websocket.send_json(event)
                except Exception:
                    return  # client gone; cleanup happens in unsubscribe/finally
        except asyncio.CancelledError:
            pass

    async def stop_listener(task_id: str) -> None:
        entry = listeners.pop(task_id, None)
        if entry is None:
            return
        subscription, task = entry
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        await stream.unsubscribe(subscription)

    async def subscribe(task_id: str) -> None:
        if task_id in listeners:
            await websocket.send_json({"type": "subscribed", "task_id": task_id})
            return
        # Subscribe before reading the snapshot so no event can slip
        # between the DB read and the redis SUBSCRIBE confirmation; queued
        # events are delivered right after the snapshot frame.
        subscription = await stream.subscribe(channel_for(task_id))
        try:
            snapshot = evaluations.get_evaluation(task_id, principal.user_id).model_dump()
        except Exception:
            await stream.unsubscribe(subscription)
            # Not owned or not found: same answer either way (no existence oracle).
            await websocket.close(code=CLOSE_FORBIDDEN, reason="task not available")
            raise WebSocketDisconnect(code=CLOSE_FORBIDDEN) from None
        listeners[task_id] = (
            subscription,
            asyncio.create_task(forward(task_id, subscription.queue)),
        )
        await websocket.send_json({"type": "task.snapshot", "task_id": task_id, "data": snapshot})
        await websocket.send_json({"type": "subscribed", "task_id": task_id})

    try:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                # malformed (non-JSON) frame: ignore and keep the session
                continue
            if not isinstance(message, dict):
                continue
            action = message.get("action")
            task_id = message.get("task_id")
            if action == "ping":
                await websocket.send_json({"type": "pong"})
            elif action == "subscribe" and isinstance(task_id, str):
                await subscribe(task_id)
            elif action == "unsubscribe" and isinstance(task_id, str):
                await stop_listener(task_id)
                await websocket.send_json({"type": "unsubscribed", "task_id": task_id})
    except WebSocketDisconnect:
        pass
    finally:
        for task_id in list(listeners):
            await stop_listener(task_id)
