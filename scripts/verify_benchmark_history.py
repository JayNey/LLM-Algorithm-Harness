"""Exercise #322 against isolated TCP API and browser; runs/tasks are explicitly seeded.

No model, Celery worker or production service is called. Requires frontend deps,
Playwright (PLAYWRIGHT_MODULE/CHROME_PATH) and the project's Python dependencies.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
import uuid
from contextlib import ExitStack
from datetime import datetime, timedelta
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.verify_frontend_first_batch import free_port, stop, wait_http  # noqa: E402


def run() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="benchmark-history-http-"))
    os.chmod(runtime, 0o700)
    api_port, ui_port = free_port(), free_port()
    api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    database_url = f"sqlite:///{runtime / 'business.sqlite3'}"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "AUTH_DATABASE_PATH": str(runtime / "auth.sqlite3"),
        "DATABASE_URL": database_url,
        "UPLOAD_DIR": str(runtime / "uploads"),
        "CORS_ORIGINS": json.dumps([ui_url]),
        "AUTH_RATE_LIMIT": "100",
        "AUTH_PROTECTED_RATE_LIMIT": "10000",
        "VITE_API_BASE_URL": api_url + "/api/v1",
        "VITE_WS_URL": f"ws://127.0.0.1:{api_port}/api/v1/ws",
        "VITE_APP_NAME": "Benchmark history acceptance",
        "BENCHMARK_HTTP_UI": ui_url,
    }
    for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        env.pop(key, None)
    with ExitStack() as stack:

        def launch(name: str, args: list[str], cwd: Path = runtime) -> subprocess.Popen:
            log = stack.enter_context((runtime / f"{name}.log").open("w", encoding="utf-8"))
            proc = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log)
            stack.callback(stop, proc)
            return proc

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
                str(api_port),
            ],
        )
        wait_http(api_url + "/api/v1/health", api)
        with httpx.Client(base_url=api_url + "/api/v1", trust_env=False) as client:
            password = secrets.token_urlsafe(24) + "!aA1"
            response = client.post(
                "/auth/register",
                json={
                    "username": "history-owner",
                    "email": "history@example.org",
                    "password": password,
                },
            )
            response.raise_for_status()
            login = client.post(
                "/auth/login", json={"username": "history-owner", "password": password}
            )
            login.raise_for_status()
            user = client.get("/users/me").json()["data"]
            headers = {"X-CSRF-Token": client.cookies["harness_csrf"]}
            response = client.post(
                "/benchmarks/suites",
                headers=headers,
                json={"name": "TCP history suite", "problems": ["p1"]},
            )
            response.raise_for_status()
            suite_id = response.json()["data"]["id"]
            from api.db.engine import make_engine, make_session_factory
            from api.db.models import AsyncTask, BenchmarkRun

            engine = make_engine(database_url)
            stack.callback(engine.dispose)
            session = make_session_factory(engine)
            now = datetime(2026, 11, 1)
            records = []
            with session() as db, db.begin():
                for index in range(27):
                    ident = str(uuid.uuid4())
                    status = "running" if index == 25 else "paused" if index == 26 else "completed"
                    db.add(
                        BenchmarkRun(
                            id=ident,
                            suite_id=suite_id,
                            user_id=user["id"],
                            status=status,
                            model="test-model",
                            config={},
                            results={"actual": {"solved": 1}},
                            accuracy=0.5 if status == "completed" else None,
                            cost_usd=None,
                            created_at=now + timedelta(minutes=index),
                            updated_at=now + timedelta(minutes=index),
                            completed_at=(
                                now + timedelta(minutes=index) if status == "completed" else None
                            ),
                        )
                    )
                    if status != "completed":
                        db.add(
                            AsyncTask(
                                id=str(uuid.uuid4()),
                                celery_task_id=str(uuid.uuid4()),
                                task_type="benchmark",
                                entity_id=ident,
                                user_id=user["id"],
                                status=status,
                                progress={
                                    "current": 1,
                                    "total": 2,
                                    "percentage": 50,
                                    "current_step": "p1",
                                },
                            )
                        )
                    records.append({"id": ident, "status": status})
            env["BENCHMARK_HTTP_SUITE"] = suite_id
            env["BENCHMARK_HTTP_RECORDS"] = json.dumps(records)
            env["BENCHMARK_HTTP_SESSION"] = json.dumps(
                {"marker": user["id"], "username": "history-owner", "expiresAt": 4102444800000}
            )
            env["BENCHMARK_HTTP_COOKIES"] = json.dumps(
                [
                    {
                        "name": c.name,
                        "value": c.value,
                        "domain": "127.0.0.1",
                        "path": c.path,
                        "httpOnly": c.name != "harness_csrf",
                        "sameSite": "Lax",
                    }
                    for c in client.cookies.jar
                ]
            )
            page = client.get(
                f"/benchmarks/suites/{suite_id}/runs", params={"limit": 20, "offset": 20}
            ).json()["data"]
            assert page["total"] == 27 and len(page["items"]) == 7 and not page["has_more"]
            assert (
                client.get(f"/benchmarks/runs/{records[0]['id']}").json()["data"]["id"]
                == records[0]["id"]
            )
        ui = launch(
            "ui",
            [
                str(ROOT / "frontend/node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                str(ui_port),
                "--strictPort",
            ],
            ROOT / "frontend",
        )
        wait_http(ui_url, ui)
        subprocess.run(
            ["node", "scripts/verify-benchmark-history-http.mjs"],
            cwd=ROOT / "frontend",
            env=env,
            check=True,
        )
    print(
        json.dumps(
            {
                "layer": "real-tcp-http-and-browser",
                "seeded": "27 benchmark runs, 2 AsyncTask states; no model calls",
                "diagnostics": str(runtime),
            }
        )
    )


if __name__ == "__main__":
    run()
