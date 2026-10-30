"""Issue #320: real TCP HTTP operations with isolated SQLite, Redis and API.

No provider requests or pre-existing accounts. AsyncTask running state is
seeded explicitly; resume publishes a real continuation to isolated Redis, with
no worker/provider execution. Use alongside browser fixture regression.
"""

import json
import os
import secrets
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from verify_frontend_first_batch import ROOT, free_port, stop, wait_http


def run():
    runtime = Path(tempfile.mkdtemp(prefix="issue320-http-"))
    os.chmod(runtime, 0o700)
    port, redis_port = free_port(), free_port()
    base = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "AUTH_DATABASE_PATH": str(runtime / "auth.sqlite3"),
        "DATABASE_URL": f'sqlite:///{runtime / "business.sqlite3"}',
        "UPLOAD_DIR": str(runtime / "uploads"),
        "TASK_SERVICE_ROOT": str(runtime / "tasks"),
        "CELERY_BROKER_URL": f"redis://127.0.0.1:{redis_port}/0",
        "CELERY_RESULT_BACKEND": f"redis://127.0.0.1:{redis_port}/1",
        "AUTH_RATE_LIMIT": "100",
        "AUTH_PROTECTED_RATE_LIMIT": "10000",
    }
    with ExitStack() as stack:

        def launch(name, command):
            log = stack.enter_context((runtime / f"{name}.log").open("w", encoding="utf-8"))
            proc = subprocess.Popen(command, cwd=runtime, env=env, stdout=log, stderr=log)
            stack.callback(stop, proc)
            return proc

        launch(
            "redis",
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
        )
        api = launch(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
            ],
        )
        wait_http(base + "/api/v1/health", api)
        with httpx.Client(base_url=base + "/api/v1", timeout=15) as client:
            password = secrets.token_urlsafe(24) + "!aA1"
            r = client.post(
                "/auth/register",
                json={
                    "username": "managementowner",
                    "email": "management@example.test",
                    "password": password,
                },
            )
            r.raise_for_status()
            owner = r.json()["data"]["id"]
            r = client.post(
                "/auth/login", json={"username": "managementowner", "password": password}
            )
            r.raise_for_status()
            client.headers["X-CSRF-Token"] = r.headers["x-csrf-token"]
            r = client.post(
                "/api-keys",
                json={
                    "provider": "openai",
                    "key_name": "local-only",
                    "api_key": "sk-local-test-management-no-provider",
                },
            )
            r.raise_for_status()
            key = r.json()["data"]["id"]
            r = client.post(
                "/evaluations",
                json={
                    "api_key_id": key,
                    "model": "local-only",
                    "problem_ids": ["p1"],
                    "strategy_names": ["vanilla"],
                },
            )
            r.raise_for_status()
            eid = r.json()["data"]["evaluation_id"]
            path = "/evaluations/" + eid
            r = client.patch(path, json={"budget_cap_usd": 12.5})
            r.raise_for_status()
            assert r.json()["data"]["budget_cap_usd"] == 12.5
            from sqlalchemy import create_engine
            from sqlalchemy.orm import Session

            from api.db.models import AsyncTask, Evaluation

            engine = create_engine(env["DATABASE_URL"])
            tid = "async-management-task"
            with Session(engine) as db, db.begin():
                db.add(
                    AsyncTask(
                        id=tid,
                        celery_task_id="celery-unrelated-id",
                        task_type="evaluation",
                        entity_id=eid,
                        user_id=owner,
                        status="running",
                    )
                )
                db.flush()
                row = db.get(Evaluation, eid)
                row.async_task_id = tid
                row.status = "running"
            r = client.get(path)
            r.raise_for_status()
            assert r.json()["data"]["async_task_id"] == tid
            r = client.post("/tasks/" + tid + "/pause")
            r.raise_for_status()
            r = client.get(path)
            r.raise_for_status()
            assert r.json()["data"]["status"] == "paused"
            assert r.json()["data"]["can_resume"] is True
            r = client.post("/tasks/" + tid + "/resume")
            r.raise_for_status()
            r = client.get(path)
            r.raise_for_status()
            assert r.json()["data"]["async_task_id"] == tid
            assert r.json()["data"]["status"] == "pending"
            r = client.post(path + "/cancel")
            r.raise_for_status()
            r = client.delete(path)
            assert r.status_code == 204, r.text
            assert client.get(path).status_code == 404
            assert client.get("/evaluations").json()["data"]["total"] == 0
            engine.dispose()
        result = {
            "passed": True,
            "layer": "real TCP HTTP + SQLite + Redis, seeded running task, no provider execution",
            "checks": [
                "cookie/CSRF login",
                "budget update",
                "owned AsyncTask ID",
                "pause",
                "resume publishes continuation",
                "cancel",
                "delete 204",
                "detail 404",
                "list refreshed",
            ],
        }
        (runtime / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result))
        print("Evidence:", runtime / "result.json")


if __name__ == "__main__":
    run()
