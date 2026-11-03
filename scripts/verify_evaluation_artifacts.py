"""Run #319 through a real TCP API and the actual Celery task implementation.

Provider/sandbox execution and broker transport use deterministic local drivers.
No results are manually injected or published, and no paid model is contacted.
All auth/business/file data is isolated in a private temporary directory.
"""

from __future__ import annotations

import csv
import io
import json
import os
import secrets
import socket
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="evaluation-artifacts-http-"))
    os.chmod(runtime, 0o700)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    database_url = f"sqlite:///{runtime / 'business.sqlite3'}"
    os.environ.update(
        {
            "SECRET_KEY": secrets.token_urlsafe(48),
            "ENCRYPTION_KEY": Fernet.generate_key().decode(),
            "AUTH_DATABASE_PATH": str(runtime / "auth.sqlite3"),
            "DATABASE_URL": database_url,
            "UPLOAD_DIR": str(runtime / "uploads"),
            "AUTH_RATE_LIMIT": "1000",
            "AUTH_PROTECTED_RATE_LIMIT": "10000",
        }
    )
    os.chdir(runtime)
    import uvicorn

    from api.db.models import AsyncTask, Evaluation
    from api.files.service import FileService
    from api.main import create_app
    from src.harness import AlgorithmHarness
    from src.models import ExecutionResult
    from src.tasks.artifacts import publish_evaluation_artifacts
    from src.tasks.evaluation import run_evaluation_task

    app = create_app(database_url=database_url)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    messages: list[dict] = []
    calls: list[str] = []
    pause_after_first: dict[str, str] = {}

    def send(name, args=(), **kwargs):
        ident = kwargs.get("task_id", str(uuid.uuid4()))
        messages.append({"name": name, "args": args, "id": ident})
        return SimpleNamespace(id=ident)

    def execute(self, config, problem, *args):
        calls.append(problem.problem_id)
        pause_id = pause_after_first.pop("task_id", None)
        if pause_id is not None:
            client.post(f"/tasks/{pause_id}/pause").raise_for_status()
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=config.name,
            generated_code="def solve(x): return x",
            status="success",
            total_tokens=37,
            difficulty=problem.difficulty,
        )

    def task_identity(evaluation_id):
        with app.state.task_session_factory() as db:
            evaluation = db.get(Evaluation, evaluation_id)
            task = db.get(AsyncTask, evaluation.async_task_id)
            return task.id, task.celery_task_id

    with ExitStack() as stack:
        stack.enter_context(patch("src.task_manager.celery_app.send_task", side_effect=send))
        stack.enter_context(
            patch(
                "src.task_manager.celery_app.AsyncResult",
                lambda *a: SimpleNamespace(state="PENDING", info=None),
            )
        )
        stack.enter_context(patch("src.tasks.evaluation.publish_progress", lambda *a, **k: None))
        stack.enter_context(patch.object(run_evaluation_task, "update_state", lambda **k: None))
        stack.enter_context(
            patch.object(AlgorithmHarness, "_prepare_strategy_runtime", lambda *a: (None, None))
        )
        stack.enter_context(patch.object(AlgorithmHarness, "_execute_problem", execute))
        stack.enter_context(
            patch.object(AlgorithmHarness, "_estimate_cost", lambda *a: (0.025, {}))
        )
        thread.start()
        try:
            deadline = time.monotonic() + 60
            while not server.started:
                if time.monotonic() >= deadline:
                    raise TimeoutError("API startup")
                time.sleep(0.05)
            base = f"http://127.0.0.1:{port}/api/v1"
            with httpx.Client(base_url=base, trust_env=False, timeout=30) as client:
                password = secrets.token_urlsafe(24) + "!aA1"
                client.post(
                    "/auth/register",
                    json={
                        "username": "artifact-owner",
                        "email": "artifact@example.org",
                        "password": password,
                    },
                ).raise_for_status()
                client.post(
                    "/auth/login", json={"username": "artifact-owner", "password": password}
                ).raise_for_status()
                client.headers["X-CSRF-Token"] = client.cookies["harness_csrf"]
                key = client.post(
                    "/api-keys",
                    json={
                        "provider": "openai",
                        "key_name": "Offline verification",
                        "api_key": "fake-offline-key",
                    },
                )
                key.raise_for_status()
                problems = [
                    {
                        "problem_id": f"p{i}",
                        "title": f"Echo {i}",
                        "description": "Return the integer input unchanged.",
                        "difficulty": "easy",
                        "tags": ["array"],
                        "test_cases": [{"input": {"x": i}, "expected_output": i}],
                    }
                    for i in (1, 2)
                ]
                client.post(
                    "/problems/upload",
                    files={
                        "file": ("problems.json", json.dumps(problems).encode(), "application/json")
                    },
                ).raise_for_status()

                def create(ids, budget=None):
                    body = {
                        "problem_ids": ids,
                        "strategy_names": ["vanilla"],
                        "api_key_id": key.json()["data"]["id"],
                        "model": "gpt-4o-mini",
                    }
                    if budget is not None:
                        body["budget_cap_usd"] = budget
                    response = client.post("/evaluations", json=body)
                    response.raise_for_status()
                    evaluation_id = response.json()["data"]["evaluation_id"]
                    client.post(f"/evaluations/{evaluation_id}/start").raise_for_status()
                    return evaluation_id

                evaluation_id = create(["p1", "p2"])
                task_id, generation = task_identity(evaluation_id)
                pause_after_first["task_id"] = task_id
                result = run_evaluation_task.apply(args=(evaluation_id,), task_id=generation).get(
                    propagate=True
                )
                assert result["status"] == "paused"
                response = client.get(f"/results/{evaluation_id}/download")
                response.raise_for_status()
                partial = response.json()
                assert (
                    partial["state"] == "paused"
                    and not partial["complete"]
                    and partial["recorded_units"] == 1
                )
                assert response.headers["x-artifact-completeness"] == "partial"
                client.post(f"/tasks/{task_id}/resume").raise_for_status()
                _, generation = task_identity(evaluation_id)
                assert (
                    run_evaluation_task.apply(args=(evaluation_id,), task_id=generation).get(
                        propagate=True
                    )["status"]
                    == "completed"
                )
                assert calls == ["p1", "p2"]
                for kind in ("json", "csv", "markdown", "html", "png", "zip"):
                    response = client.get(
                        f"/results/{evaluation_id}/download", params={"format": kind}
                    )
                    response.raise_for_status()
                    assert response.headers["x-artifact-completeness"] == "complete"
                    if kind == "json":
                        assert response.json()["recorded_units"] == 2
                        assert (
                            response.json()["results"]["vanilla"][0]["execution"]["total_tokens"]
                            == 37
                        )
                    elif kind == "csv":
                        assert (
                            len(
                                list(
                                    csv.DictReader(
                                        io.StringIO(response.content.decode("utf-8-sig"))
                                    )
                                )
                            )
                            == 2
                        )
                    elif kind == "png":
                        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
                    elif kind == "zip":
                        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
                            assert (
                                len(bundle.namelist()) == 5
                                and json.loads(bundle.read("results.json"))["complete"]
                            )
                    else:
                        assert "Complete evaluation results" in response.text
                    (runtime / f"result.{kind}").write_bytes(response.content)

                failure_id = create(["p1"])
                _, generation = task_identity(failure_id)
                original = FileService._persist

                def broken_files(self, user_id, data, suffix, filename, category, *args, **kwargs):
                    if category == "results":
                        raise OSError("Controlled publication failure")
                    return original(
                        self, user_id, data, suffix, filename, category, *args, **kwargs
                    )

                with patch.object(FileService, "_persist", broken_files):
                    assert (
                        run_evaluation_task.apply(args=(failure_id,), task_id=generation).get(
                            propagate=True
                        )["status"]
                        == "completed"
                    )
                state = client.get(f"/results/{failure_id}/publication").json()["data"]
                assert state["status"] == "failed" and not state["available"]
                before = len(calls)
                client.post(f"/results/{failure_id}/publication/retry").raise_for_status()
                message = next(
                    m
                    for m in reversed(messages)
                    if m["name"] == "src.tasks.artifacts.publish_evaluation_artifacts"
                )
                assert publish_evaluation_artifacts.apply(
                    args=message["args"], task_id=message["id"]
                ).get(propagate=True)["available"]
                assert len(calls) == before
                assert client.get(f"/results/{failure_id}/download").status_code == 200
                print(
                    json.dumps(
                        {
                            "layer": "real-tcp-http-worker",
                            "scenarios": [
                                "import_and_create",
                                "pause_partial_download",
                                "resume_complete_download",
                                "six_formats",
                                "publication_failure_isolation",
                                "independent_retry_without_model_calls",
                            ],
                            "formats": 6,
                            "model_driver_calls": len(calls),
                            "provider_sandbox_broker_backend": "controlled substitutes",
                            "manual_result_injection": False,
                            "diagnostics": str(runtime),
                        }
                    ),
                    flush=True,
                )
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            if thread.is_alive():
                raise RuntimeError("API did not stop")


if __name__ == "__main__":
    run()
