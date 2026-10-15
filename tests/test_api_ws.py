"""WebSocket progress streaming tests (issue #150)."""

import asyncio
import secrets

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from api.auth.config import AuthSettings
from api.files.config import FileSettings
from api.main import create_app
from api.progress import ProgressStream, channel_for

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"


class FakeProgressStream(ProgressStream):
    """In-memory stream the tests push events through."""

    def __init__(self):
        self.queues: dict[str, list[asyncio.Queue]] = {}

    async def subscribe(self, channel):
        queue: asyncio.Queue = asyncio.Queue()
        self.queues.setdefault(channel, []).append(queue)
        return queue

    async def unsubscribe(self, channel, queue):
        queues = self.queues.get(channel, [])
        if queue in queues:
            queues.remove(queue)

    async def emit(self, channel, event):
        for queue in self.queues.get(channel, []):
            await queue.put(event)


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


@pytest.fixture
def env(tmp_path):
    stream = FakeProgressStream()
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        progress_stream=stream,
    )
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
        )
        assert register.status_code == 201, register.text
        tokens = client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
        ).json()["data"]
        key_id = client.post(
            "/api/v1/api-keys",
            headers={"Authorization": "Bearer " + tokens["access_token"]},
            json={"provider": "openai", "key_name": "t", "api_key": KEY},
        ).json()["data"]["id"]
        # one owned evaluation in pending state (snapshot source)
        created = client.post(
            "/api/v1/evaluations",
            headers={"Authorization": "Bearer " + tokens["access_token"]},
            json={
                "api_key_id": key_id,
                "problem_ids": ["p1"],
                "strategy_names": ["vanilla"],
                "model": "gpt-test",
            },
        )
        evaluation_id = created.json()["data"]["evaluation_id"]

        # a second user for the cross-user case
        client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.org", "password": PASSWORD},
        )
        bob_tokens = client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": PASSWORD}
        ).json()["data"]

        yield {
            "client": client,
            "token": tokens["access_token"],
            "bob_token": bob_tokens["access_token"],
            "evaluation_id": evaluation_id,
            "stream": stream,
        }


def _connect(client, token):
    return client.websocket_connect(f"/api/v1/ws/progress?token={token}")


class TestAuthentication:
    def test_invalid_token_is_rejected_4401(self, env):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with _connect(env["client"], "not-a-token") as ws:
                ws.receive_json()
        assert excinfo.value.code == 4401

    def test_missing_token_is_rejected(self, env):
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with env["client"].websocket_connect("/api/v1/ws/progress") as ws:
                ws.receive_json()
        assert excinfo.value.code == 4401


class TestSubscription:
    def test_subscribe_sends_snapshot_and_forwards_events(self, env):
        client = env["client"]
        stream = env["stream"]
        evaluation_id = env["evaluation_id"]

        with _connect(client, env["token"]) as ws:
            connected = ws.receive_json()
            assert connected["type"] == "connected"

            ws.send_json({"action": "subscribe", "task_id": evaluation_id})
            snapshot = ws.receive_json()
            assert snapshot["type"] == "task.snapshot"
            assert snapshot["data"]["evaluation_id"] == evaluation_id
            assert snapshot["data"]["status"] == "pending"
            assert ws.receive_json()["type"] == "subscribed"

            channel = channel_for(evaluation_id)
            event = {"type": "task.progress", "task_id": evaluation_id, "data": {"n": 1}}
            asyncio.run(stream.emit(channel, event))
            assert ws.receive_json() == event

    def test_cross_user_subscription_is_denied_4403(self, env):
        client = env["client"]
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with _connect(client, env["bob_token"]) as ws:
                ws.receive_json()
                ws.send_json({"action": "subscribe", "task_id": env["evaluation_id"]})
                ws.receive_json()
        assert excinfo.value.code == 4403

    def test_unsubscribe_stops_forwarding(self, env):
        client = env["client"]
        stream = env["stream"]
        evaluation_id = env["evaluation_id"]
        channel = channel_for(evaluation_id)

        with _connect(client, env["token"]) as ws:
            ws.receive_json()
            ws.send_json({"action": "subscribe", "task_id": evaluation_id})
            ws.receive_json()  # snapshot
            ws.receive_json()  # subscribed

            ws.send_json({"action": "unsubscribe", "task_id": evaluation_id})
            assert ws.receive_json()["type"] == "unsubscribed"
            assert stream.queues.get(channel) == []

            # events after unsubscribe are dropped by the stream, not queued
            asyncio.run(stream.emit(channel, {"type": "task.progress", "data": {}}))

    def test_ping_pong(self, env):
        with _connect(env["client"], env["token"]) as ws:
            ws.receive_json()
            ws.send_json({"action": "ping"})
            assert ws.receive_json()["type"] == "pong"


class TestPublishHelper:
    def test_publish_returns_false_when_redis_down(self):
        from api.progress import publish_progress

        class BrokenClient:
            def publish(self, channel, payload):
                raise ConnectionError("redis down")

        assert (
            publish_progress("t1", "task.progress", {"a": 1}, redis_client=BrokenClient()) is False
        )

    def test_publish_delivers_json_to_channel(self):
        import json as jsonlib

        from api.progress import publish_progress

        captured = {}

        class StubClient:
            def publish(self, channel, payload):
                captured["channel"] = channel
                captured["payload"] = jsonlib.loads(payload)
                return 1

        assert publish_progress("t2", "task.started", {"s": 1}, redis_client=StubClient()) is True
        assert captured["channel"] == "progress:t2"
        assert captured["payload"]["type"] == "task.started"
        assert captured["payload"]["data"] == {"s": 1}
        assert "timestamp" in captured["payload"]
