"""WebSocket endpoint for live evaluation progress (issue #150)."""

import asyncio

from anyio import CancelScope
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from api.auth.cookies import ACCESS_COOKIE
from api.progress import Subscription, channel_for

router = APIRouter(prefix="/api/v1")

CLOSE_INVALID_TOKEN = 4401
CLOSE_FORBIDDEN = 4403
CLOSE_INTERNAL = 1011
AUTH_RECHECK_INTERVAL = 1.0


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
    credential = token or websocket.cookies.get(ACCESS_COOKIE, "")

    await websocket.accept()
    try:
        principal = auth.authenticate(credential)
    except Exception:
        await websocket.close(code=CLOSE_INVALID_TOKEN, reason="invalid token")
        return

    # task_id -> (subscription, forwarder task)
    listeners: dict[str, tuple[Subscription, asyncio.Task | None]] = {}
    send_lock = asyncio.Lock()
    closed = asyncio.Event()

    def authenticate() -> None:
        try:
            auth.authenticate(credential)
        except Exception:
            raise WebSocketDisconnect(code=CLOSE_INVALID_TOKEN) from None

    async def close_locked(code: int, reason: str) -> None:
        # All sends and server-initiated closes share the same lock.
        if not closed.is_set():
            try:
                await websocket.close(code=code, reason=reason)
            finally:
                closed.set()

    async def send_json(frame: dict) -> None:
        async with send_lock:
            if closed.is_set():
                raise WebSocketDisconnect(code=CLOSE_INVALID_TOKEN)
            try:
                authenticate()
            except WebSocketDisconnect:
                await close_locked(CLOSE_INVALID_TOKEN, "invalid token")
                raise
            await websocket.send_json(frame)

    async def watch_auth() -> None:
        while True:
            await asyncio.sleep(AUTH_RECHECK_INTERVAL)
            authenticate()

    async def forward(task_id: str, queue: asyncio.Queue) -> None:
        try:
            while True:
                event = await queue.get()
                try:
                    await send_json(event)
                except Exception:
                    closed.set()  # wake the owner even while it is awaiting a client frame
                    return
        except asyncio.CancelledError:
            pass

    async def stop_listener(task_id: str) -> None:
        entry = listeners.get(task_id)
        if entry is None:
            return
        subscription, task = entry
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await stream.unsubscribe(subscription)
        listeners.pop(task_id, None)

    async def subscribe(task_id: str) -> None:
        if task_id in listeners:
            await send_json({"type": "subscribed", "task_id": task_id})
            return
        # Subscribe before reading the snapshot so no event can slip
        # between the DB read and the redis SUBSCRIBE confirmation; queued
        # events are delivered right after the snapshot frame.
        subscription = await stream.subscribe(channel_for(task_id))
        # Register immediately so the owner's finally also covers invalidation
        # or cancellation before the snapshot and forwarder are ready.
        listeners[task_id] = (subscription, None)
        authenticate()
        try:
            snapshot = evaluations.get_evaluation(task_id, principal.user_id).model_dump()
        except Exception:
            # Not owned or not found: same answer either way (no existence oracle).
            async with send_lock:
                await close_locked(CLOSE_FORBIDDEN, "task not available")
            raise WebSocketDisconnect(code=CLOSE_FORBIDDEN) from None
        await send_json({"type": "task.snapshot", "task_id": task_id, "data": snapshot})
        await send_json({"type": "subscribed", "task_id": task_id})
        listeners[task_id] = (
            subscription,
            asyncio.create_task(forward(task_id, subscription.queue)),
        )

    async def receive_messages() -> None:
        while True:
            try:
                message = await websocket.receive_json()
            except WebSocketDisconnect:
                raise
            except Exception:
                # malformed (non-JSON) frame: ignore and keep the session
                continue
            authenticate()
            if not isinstance(message, dict):
                continue
            action = message.get("action")
            task_id = message.get("task_id")
            if action == "ping":
                await send_json({"type": "pong"})
            elif action == "subscribe" and isinstance(task_id, str):
                await subscribe(task_id)
            elif action == "unsubscribe" and isinstance(task_id, str):
                await stop_listener(task_id)
                await send_json({"type": "unsubscribed", "task_id": task_id})

    background: list[asyncio.Task] = []
    try:
        await send_json({"type": "connected", "user_id": principal.user_id})
        background = [
            asyncio.create_task(receive_messages()),
            asyncio.create_task(watch_auth()),
            asyncio.create_task(closed.wait()),
        ]
        done, _ = await asyncio.wait(background, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except WebSocketDisconnect as exc:
        if exc.code == CLOSE_INVALID_TOKEN:
            async with send_lock:
                await close_locked(CLOSE_INVALID_TOKEN, "invalid token")
    finally:
        # ASGI hosts may cancel the handler as soon as the peer disconnects.
        # Finish releasing subscriptions even under that cancellation scope.
        with CancelScope(shield=True):
            for task in background:
                task.cancel()
            await asyncio.gather(*background, return_exceptions=True)
            for task_id in list(listeners):
                await stop_listener(task_id)
