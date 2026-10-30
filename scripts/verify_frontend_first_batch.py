"""Run F1/F4/F8 browser acceptance against isolated real local services.

Requires the project's Python/frontend dependencies, redis-server and Playwright
Chromium. Set PLAYWRIGHT_MODULE to an installed Playwright module if necessary.
No provider calls, existing accounts, databases or Redis instances are used.
"""

from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_http(url: str, process: subprocess.Popen) -> None:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Service exited with {process.returncode}: {url}")
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise TimeoutError(url)


def stop(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def run() -> None:
    # Keep diagnostics on failure; all generated credentials are ephemeral.
    runtime = Path(tempfile.mkdtemp(prefix="pr313-acceptance-"))
    os.chmod(runtime, 0o700)
    print(f"Diagnostics: {runtime}", flush=True)
    api_port, ui_port, redis_port = free_port(), free_port(), free_port()
    api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "AUTH_DATABASE_PATH": str(runtime / "auth.sqlite3"),
        "DATABASE_URL": f"sqlite:///{runtime / 'business.sqlite3'}",
        "UPLOAD_DIR": str(runtime / "uploads"),
        "TASK_SERVICE_ROOT": str(runtime / "tasks"),
        "CORS_ORIGINS": json.dumps([ui_url]),
        "CELERY_BROKER_URL": f"redis://127.0.0.1:{redis_port}/0",
        "CELERY_RESULT_BACKEND": f"redis://127.0.0.1:{redis_port}/1",
        "AUTH_RATE_LIMIT": "100",
        "AUTH_PROTECTED_RATE_LIMIT": "10000",
        "VITE_API_BASE_URL": api_url + "/api/v1",
        "VITE_WS_URL": f"ws://127.0.0.1:{api_port}/api/v1/ws",
        "VITE_APP_NAME": "PR313 acceptance",
        "FIRST_BATCH_UI_URL": ui_url,
        "FIRST_BATCH_API_URL": api_url,
        "FIRST_BATCH_PASSWORD": secrets.token_urlsafe(24) + "!aA1",
        "FIRST_BATCH_OUT": str(runtime / "browser.json"),
    }
    with ExitStack() as stack:

        def launch(name: str, args: list[str], cwd: Path = runtime) -> subprocess.Popen:
            log = stack.enter_context((runtime / f"{name}.log").open("w"))
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log)
            stack.callback(stop, process)
            return process

        redis = launch(
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
        from redis import Redis
        from redis.exceptions import ConnectionError as RedisConnectionError

        broker = Redis(host="127.0.0.1", port=redis_port)
        for _ in range(100):
            try:
                if broker.ping():
                    break
            except RedisConnectionError:
                pass
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise RuntimeError(f"Redis failed to start: {redis.poll()}")
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
        launch(
            "worker",
            [
                sys.executable,
                "-m",
                "celery",
                "-A",
                "src.celery_app",
                "worker",
                "--pool=solo",
                "--concurrency=1",
                "--queues=default",
                "--without-gossip",
                "--without-mingle",
                "--without-heartbeat",
                "--loglevel=INFO",
            ],
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
        response = httpx.post(
            api_url + "/api/v1/auth/register",
            json={
                "username": "pr313owner",
                "email": "pr313@example.org",
                "password": env["FIRST_BATCH_PASSWORD"],
            },
        )
        response.raise_for_status()
        owner = response.json()["data"]["id"]
        # Seed result rows, not report bytes: the real report service renders them.
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from api.db.models import Evaluation, EvaluationResult, Problem

        engine = create_engine(env["DATABASE_URL"])
        with Session(engine) as db:
            db.add(
                Problem(
                    id="pr313-problem",
                    problem_id="pr313-sum",
                    title="PR313 Sum",
                    difficulty="easy",
                    tags=["array"],
                )
            )
            for suffix, status, user in [
                ("complete", "completed", owner),
                ("partial", "failed", owner),
                ("other", "completed", "another-owner"),
            ]:
                db.add(
                    Evaluation(
                        id=f"pr313-{suffix}",
                        user_id=user,
                        run_id=f"pr313-run-{suffix}",
                        status=status,
                        strategy_names=["vanilla"],
                        problem_ids=["pr313-sum"],
                        problem_count=1,
                        completed_count=1 if status == "completed" else 0,
                        model="local-seeded-result",
                    )
                )
                db.flush()
                db.add(
                    EvaluationResult(
                        id=f"pr313-result-{suffix}",
                        evaluation_id=f"pr313-{suffix}",
                        problem_id="pr313-sum",
                        strategy_name="vanilla",
                        status="success",
                        metrics={
                            "success": True,
                            "total_tokens": 10,
                            "iterations": 1,
                            "cost_usd": 0.0,
                            "cost_unknown": False,
                            "execution_time_seconds": 0.1,
                        },
                    )
                )
            db.commit()
        engine.dispose()
        subprocess.run(
            ["node", str(ROOT / "frontend/scripts/verify-first-batch-live.mjs")],
            cwd=runtime,
            env=env,
            check=True,
        )
        print(
            f"PASS: real API + Redis/Celery + Chromium acceptance; evidence: {runtime / 'browser.json'}"
        )


if __name__ == "__main__":
    run()
