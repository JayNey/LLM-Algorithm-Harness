"""Offline HTTP/SQLite workflows for issue #158 section 4.

Real routes, auth, task orchestration, strategies, checkpoints and reports;
only model, sandbox and queue/Redis transports are replaced.

Run from the repository root:
    python3 -m pytest tests/integration/test_api_workflows.py -o addopts= -q

The focused run disables the repository-wide coverage gate. No Redis, Docker
or provider credentials are required. Provider replies include fixed usage and
billing metadata (USD 0.01 per call); production cost aggregation stays real.
Queue draining executes real Celery task bodies in-process, so this does not
replace tests/test_async_task_integration.py's real broker/worker coverage.

Section 4 mapping: the first three tests cover the three business workflows;
the remaining tests cover concurrent HTTP requests, budget boundaries and
pause/restart/checkpoint recovery. Every database, upload, checkpoint and
experiment artifact is confined to pytest's temporary directory.

"""

from collections import deque
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.config import settings
from api.db.problem_store import ProblemStore
from api.files.config import FileSettings
from api.main import create_app
from src.celery_app import celery_app
from src.llm_client import LLMClient
from src.models import LLMResponse, SandboxResult, TokenUsage
from src.sandbox_executor import SandboxExecutor
from src.tasks.evaluation import run_evaluation_task
from src.tasks.experiment import run_experiment_task

pytestmark = pytest.mark.integration
PASSWORD = "integration-password-158!"


def problem(pid):
    return {
        "problem_id": pid,
        "title": f"Return x ({pid})",
        "description": "Return x from the input.",
        "difficulty": "easy",
        "tags": ["array"],
        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
    }


def data(response, status=200):
    assert response.status_code == status, response.text
    assert response.json()["success"] is True
    return response.json()["data"]


def account(client, name="alice"):
    data(
        client.post(
            "/api/v1/auth/register",
            json={
                "username": name,
                "email": f"{name}@example.org",
                "password": PASSWORD,
            },
        ),
        201,
    )
    tokens = data(
        client.post(
            "/api/v1/auth/login",
            json={
                "username": name,
                "password": PASSWORD,
            },
        )
    )
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    key = data(
        client.post(
            "/api/v1/api-keys",
            headers=headers,
            json={
                "provider": "openai",
                "key_name": "offline",
                "api_key": "sk-offline-test-only",
            },
        ),
        201,
    )
    return headers, key["id"]


@pytest.fixture
def environment(tmp_path, monkeypatch):
    # Relative worker checkpoints and experiment output must never touch repo data.
    monkeypatch.chdir(tmp_path)
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY="integration-test-only-secret-key-158",
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=100,
    )
    for key in ("SECRET_KEY", "ENCRYPTION_KEY"):
        monkeypatch.setenv(key, getattr(auth, key).get_secret_value())
    monkeypatch.setenv("AUTH_DATABASE_PATH", str(auth.AUTH_DATABASE_PATH))
    files = FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads")
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    monkeypatch.setattr(settings, "DATABASE_URL", f"sqlite:///{tmp_path / 'business.sqlite3'}")
    queue = deque()

    def send_task(name, args=(), kwargs=None, **options):
        queue.append((name, args, kwargs or {}))
        return SimpleNamespace(id=str(uuid4()))

    monkeypatch.setattr(celery_app, "send_task", send_task)
    monkeypatch.setattr(celery_app, "AsyncResult", lambda *a, **k: SimpleNamespace(state="PENDING"))
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda **kwargs: None)
    monkeypatch.setattr("src.tasks.evaluation.publish_progress", lambda *a, **k: None)
    monkeypatch.setattr(LLMClient, "_initialize_client", lambda self: None)
    generated = []

    def generate(self, *args, **kwargs):
        generated.append(self.config.model)
        return LLMResponse(
            text="```python\ndef solution(x):\n    return x\n```",
            model=self.config.model,
            usage=TokenUsage(prompt_tokens=1000, completion_tokens=1000, total_tokens=2000),
            finish_reason="stop",
            pricing_metadata={
                "model": self.config.model,
                "total_cost": 0.01,
                "usage_known": True,
                "pricing_known": True,
                "source": "test-fixture",
            },
        )

    monkeypatch.setattr(LLMClient, "generate", generate)
    monkeypatch.setattr(SandboxExecutor, "health_check", lambda self: (True, None))
    monkeypatch.setattr(
        SandboxExecutor,
        "execute",
        lambda *a, **k: SandboxResult(
            status="success",
            all_passed=True,
            execution_time=0.01,
        ),
    )

    @contextmanager
    def open_app():
        app = create_app(auth, files, database_url=settings.DATABASE_URL)
        with TestClient(app) as client:
            yield client, app

    def drain(max_workers=1):
        tasks = {
            run_evaluation_task.name: run_evaluation_task,
            run_experiment_task.name: run_experiment_task,
        }

        def execute(message):
            name, args, kwargs = message
            tasks[name].run(*args, **kwargs)

        messages = list(queue)
        queue.clear()
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            list(pool.map(execute, messages))

    return SimpleNamespace(session=open_app, drain=drain, queue=queue, generated=generated)


def create_evaluation(client, headers, key, ids=("p1",), **options):
    return data(
        client.post(
            "/api/v1/evaluations",
            headers=headers,
            json={
                "problem_ids": list(ids),
                "strategy_names": ["vanilla"],
                "api_key_id": key,
                "model": "gpt-4o-mini",
                **options,
            },
        ),
        201,
    )["evaluation_id"]


def start(client, headers, evaluation):
    return data(client.post(f"/api/v1/evaluations/{evaluation}/start", headers=headers), 202)


def result(client, headers, evaluation):
    return data(client.get(f"/api/v1/results/{evaluation}", headers=headers))


def test_register_login_create_task_and_query_results(environment):
    with environment.session() as (client, app):
        headers, key = account(client)
        ProblemStore(app.state.task_session_factory).upsert_import([problem("p1")])
        evaluation = create_evaluation(client, headers, key)
        pending = start(client, headers, evaluation)
        assert pending["status"] == "pending"
        assert result(client, headers, evaluation)["problems"]["total"] == 0
        environment.drain()
        detail = result(client, headers, evaluation)
        assert detail["status"] == "completed"
        assert detail["problems"]["total"] == 1
        assert detail["problems"]["items"][0]["status"] == "success"
        task = data(
            client.get(f"/api/v1/tasks/{task_id(client, headers, evaluation)}", headers=headers)
        )
        assert task["status"] == "completed"
        assert task["progress"]["percentage"] == 100
        assert environment.generated == ["gpt-4o-mini"]
        other, _ = account(client, "bob")
        assert client.get(f"/api/v1/results/{evaluation}", headers=other).status_code == 404


def test_upload_evaluate_wait_and_download_report(environment):
    import json

    with environment.session() as (client, app):
        headers, key = account(client)
        uploaded = data(
            client.post(
                "/api/v1/problems/upload",
                headers=headers,
                files={
                    "file": (
                        "problems.json",
                        json.dumps([problem("uploaded-only")]),
                        "application/json",
                    )
                },
            )
        )
        assert uploaded["validation"]["imported"] == 1
        assert (
            client.get("/api/v1/problems/export", headers=headers).json()[0]["problem_id"]
            == "uploaded-only"
        )
        evaluation = create_evaluation(client, headers, key, ids=("uploaded-only",))
        start(client, headers, evaluation)
        environment.drain()
        detail = result(client, headers, evaluation)
        assert detail["status"] == "completed"
        assert detail["problems"]["items"][0]["status"] == "success", detail
        for format_name in ("markdown", "html", "csv"):
            report = client.get(f"/api/v1/reports/{format_name}/{evaluation}", headers=headers)
            assert report.status_code == 200, report.text
            assert report.headers["content-disposition"].startswith("attachment")
            assert "vanilla" in report.text
            if format_name == "csv":
                assert "uploaded-only" in report.text
            elif format_name == "markdown":
                assert "100.0%" in report.text
        assert environment.generated == ["gpt-4o-mini"]


def test_create_run_experiment_and_compare_models(environment, tmp_path):
    import json

    (tmp_path / "dataset.json").write_text(json.dumps([problem("exp-p1")]), encoding="utf-8")
    with environment.session() as (client, app):
        headers, key = account(client)
        experiment = data(
            client.post(
                "/api/v1/experiments",
                headers=headers,
                json={
                    "name": "integration-comparison",
                    "dataset_path": "dataset.json",
                    "models": [{"model": "gpt-4o-mini"}, {"model": "gpt-4o"}],
                    "strategies": [{"name": "vanilla"}],
                    "repeats": 1,
                    "api_key_id": key,
                },
            ),
            201,
        )["id"]
        pending = data(client.post(f"/api/v1/experiments/{experiment}/run", headers=headers), 202)
        assert pending["status"] == "pending"
        environment.drain()
        finished = data(client.get(f"/api/v1/experiments/{experiment}", headers=headers))
        assert finished["status"] == "completed", finished.get("error_message")
        comparison = data(
            client.get(f"/api/v1/experiments/{experiment}/comparison", headers=headers)
        )
        assert {combo["model"] for combo in comparison["combinations"]} == {"gpt-4o-mini", "gpt-4o"}
        assert all(combo["solved"] == 1 for combo in comparison["combinations"])
        assert sorted(environment.generated) == ["gpt-4o", "gpt-4o-mini"]


def task_id(client, headers, evaluation):
    tasks = data(client.get("/api/v1/tasks", headers=headers))["items"]
    return next(task["id"] for task in tasks if task["entity_id"] == evaluation)


def test_concurrent_evaluation_creation_keeps_tasks_and_results_separate(environment, monkeypatch):
    with environment.session() as (client, app):
        headers, key = account(client)
        ProblemStore(app.state.task_session_factory).upsert_import([problem("p1"), problem("p2")])
        barrier = Barrier(2)

        def create(pid):
            barrier.wait(timeout=5)
            evaluation = create_evaluation(client, headers, key, ids=(pid,))
            start(client, headers, evaluation)
            return evaluation

        with ThreadPoolExecutor(max_workers=2) as pool:
            ids = list(pool.map(create, ("p1", "p2")))
        assert len(set(ids)) == 2
        assert len(environment.queue) == 2
        execution_barrier = Barrier(2)

        def sandbox(*args, **kwargs):
            execution_barrier.wait(timeout=10)
            return SandboxResult(status="success", all_passed=True)

        monkeypatch.setattr(SandboxExecutor, "execute", sandbox)
        environment.drain(max_workers=2)
        for evaluation, pid in zip(ids, ("p1", "p2"), strict=True):
            detail = result(client, headers, evaluation)
            assert detail["status"] == "completed"
            assert detail["problems"]["total"] == 1
            assert detail["problems"]["items"][0]["problem_id"] == pid
        assert len(environment.generated) == 2


@pytest.mark.parametrize("cap, expected_calls", [(0, 0), (0.000000001, 1)])
def test_budget_stops_dispatch_and_resume_does_not_bypass_cap(environment, cap, expected_calls):
    from src.task_service import TaskService

    with environment.session() as (client, app):
        headers, key = account(client)
        ProblemStore(app.state.task_session_factory).upsert_import([problem("p1"), problem("p2")])
        evaluation = create_evaluation(client, headers, key, ids=("p1", "p2"), budget_cap_usd=cap)
        start(client, headers, evaluation)
        environment.drain()
        paused = data(client.get(f"/api/v1/evaluations/{evaluation}", headers=headers))
        assert paused["status"] == "paused"
        assert len(environment.generated) == expected_calls
        assert result(client, headers, evaluation)["problems"]["total"] == expected_calls
        assert (paused["spent_usd"] > 0) is bool(expected_calls)
        checkpoint = TaskService(root=f"data/tasks/{evaluation}").get(f"eval-{evaluation}")
        assert checkpoint.state == "paused"
        assert checkpoint.completed_units == expected_calls
        identity = task_id(client, headers, evaluation)
        data(client.post(f"/api/v1/tasks/{identity}/resume", headers=headers))
        environment.drain()
        again = data(client.get(f"/api/v1/evaluations/{evaluation}", headers=headers))
        assert again["status"] == "paused"
        assert again["spent_usd"] == paused["spent_usd"]
        assert len(environment.generated) == expected_calls
        assert result(client, headers, evaluation)["problems"]["total"] == expected_calls


def test_pause_restart_resume_uses_checkpoint_without_repeating_work(environment, monkeypatch):
    from src.task_service import TaskService

    with environment.session() as (client, app):
        headers, key = account(client)
        ProblemStore(app.state.task_session_factory).upsert_import([problem("p1"), problem("p2")])
        evaluation = create_evaluation(client, headers, key, ids=("p1", "p2"))
        start(client, headers, evaluation)
        identity = task_id(client, headers, evaluation)
        executed = []

        def sandbox(self, code, problem, **kwargs):
            executed.append(problem.problem_id)
            if len(executed) == 1:
                data(client.post(f"/api/v1/tasks/{identity}/pause", headers=headers))
            return SandboxResult(status="success", all_passed=True)

        monkeypatch.setattr(SandboxExecutor, "execute", sandbox)
        environment.drain()
        paused = data(client.get(f"/api/v1/evaluations/{evaluation}", headers=headers))
        assert paused["status"] == "paused"
        first = result(client, headers, evaluation)["problems"]["items"]
        assert len(first) == 1
        checkpoint = TaskService(root=f"data/tasks/{evaluation}").get(f"eval-{evaluation}")
        assert checkpoint.state == "paused"
        assert checkpoint.completed_units == 1

    # Close the original app and reopen the same databases, keys and checkpoint tree.
    with environment.session() as (client, app):
        persisted = data(client.get(f"/api/v1/evaluations/{evaluation}", headers=headers))
        assert persisted["status"] == "paused"
        resumed = data(client.post(f"/api/v1/tasks/{identity}/resume", headers=headers))
        assert resumed["id"] == identity and resumed["status"] == "pending"
        environment.drain()
        detail = result(client, headers, evaluation)
        assert detail["status"] == "completed"
        assert detail["problems"]["total"] == 2
        assert sorted(executed) == ["p1", "p2"]
        assert len(environment.generated) == 2
        finished = data(client.get(f"/api/v1/evaluations/{evaluation}", headers=headers))
        assert finished["spent_usd"] == pytest.approx(paused["spent_usd"] * 2)
        assert first[0] in detail["problems"]["items"]


def test_uploaded_problems_are_owner_scoped_and_override_shared_ids(environment, monkeypatch):
    import json

    with environment.session() as (client, app):
        alice, alice_key = account(client)
        bob, bob_key = account(client, "bob")
        # An owner's private version of a shared ID must take precedence;
        # another user's private-only ID must remain unavailable.
        shared = problem("collision")
        shared["title"] = "Shared version"
        ProblemStore(app.state.task_session_factory).upsert_import([shared])
        private = [problem("collision"), problem("alice-only")]
        private[0]["title"] = "Alice version"
        data(
            client.post(
                "/api/v1/problems/upload",
                headers=alice,
                files={
                    "file": ("private.json", json.dumps(private), "application/json"),
                },
            )
        )
        seen = []

        def sandbox(self, code, problem, **kwargs):
            seen.append((problem.problem_id, problem.title))
            return SandboxResult(status="success", all_passed=True)

        monkeypatch.setattr(SandboxExecutor, "execute", sandbox)
        alice_eval = create_evaluation(client, alice, alice_key, ids=("collision",))
        bob_eval = create_evaluation(client, bob, bob_key, ids=("collision", "alice-only"))
        start(client, alice, alice_eval)
        start(client, bob, bob_eval)
        environment.drain()
        assert ("collision", "Alice version") in seen
        assert ("collision", "Shared version") in seen
        assert not any(pid == "alice-only" for pid, _ in seen)
        assert result(client, alice, alice_eval)["problems"]["items"][0]["status"] == "success"
        items = result(client, bob, bob_eval)["problems"]["items"]
        assert {item["problem_id"]: item["status"] for item in items} == {
            "collision": "success",
            "alice-only": "failed",
        }
        assert len(environment.generated) == 2
