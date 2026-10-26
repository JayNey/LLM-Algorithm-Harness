"""Real task writes read back through authenticated log APIs."""

import json
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from test_api_monitoring_queue_compatibility import make_app, signup

from api.db.models import AsyncTask, Evaluation
from src.task_manager import TaskManager


@pytest.fixture
def api(tmp_path, monkeypatch):
    app = make_app(tmp_path)
    with TestClient(app) as client:
        auth = app.state.auth
        monkeypatch.setenv("AUTH_DATABASE_PATH", str(auth.settings.AUTH_DATABASE_PATH))
        monkeypatch.setenv("SECRET_KEY", auth.settings.SECRET_KEY.get_secret_value())
        monkeypatch.setenv("ENCRYPTION_KEY", auth.settings.ENCRYPTION_KEY.get_secret_value())
        alice, headers = signup(client, "alice")
        bob, other = signup(client, "bob")
        app.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(alice)]
        yield app, client, alice, headers, bob, other


def seed(app, owner, task_type="evaluation"):
    task_id, entity_id = str(uuid4()), str(uuid4())
    with Session(app.state.monitor.task_engine) as db:
        task = AsyncTask(
            id=task_id,
            entity_id=entity_id,
            user_id=owner,
            task_type=task_type,
            celery_task_id=str(uuid4()),
            status="pending",
        )
        db.add(task)
        if task_type == "evaluation":
            db.add(
                Evaluation(
                    id=entity_id,
                    user_id=owner,
                    status="pending",
                    async_task_id=task_id,
                    strategy_names=["vanilla"],
                    problem_ids=["p1"],
                )
            )
        db.commit()
    return task_id, entity_id


def logs(client, credentials, task_id, **params):
    return client.get(f"/api/v1/logs/tasks/{task_id}", headers=credentials, params=params)


@pytest.mark.parametrize(
    "task_type", ["evaluation", "experiment", "benchmark", "import", "ab_test"]
)
def test_committed_worker_states_are_owned_and_downloadable(api, task_type):
    app, client, owner, headers, _, other = api
    task_id, entity_id = seed(app, owner, task_type)
    with Session(app.state.monitor.task_engine) as db:
        manager = TaskManager(db)
        manager.update_task_status(task_id, "running")
        manager.update_task_progress(
            task_id, {"current": 1, "total": 2, "message": "private body"}, "running"
        )
        manager.update_task_status(task_id, "failed", "password=private-error")
    response = logs(client, headers, task_id)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]["items"]
    assert [row["message"] for row in rows] == ["task.failed", "task.progress", "task.started"]
    assert "private" not in json.dumps(rows)
    if task_type == "evaluation":
        assert logs(client, headers, entity_id).json()["data"]["items"] == rows
    for identifier in [task_id] + ([entity_id] if task_type == "evaluation" else []):
        assert logs(client, other, identifier).status_code == 404
        assert logs(client, {}, identifier).status_code == 401
        assert client.get(f"/api/v1/logs/download/{identifier}", headers=other).status_code == 404
    assert client.get("/api/v1/logs", headers=other).status_code == 403
    assert client.get("/api/v1/logs", headers=headers).status_code == 200
    filtered = logs(client, headers, task_id, level="error", search="task.failed").json()["data"]
    assert filtered["total"] == 1
    download = client.get(
        f"/api/v1/logs/download/{task_id}",
        headers=headers,
        params={"level": "error", "search": "task.failed", "limit": 1, "offset": 100},
    )
    assert download.status_code == 200
    assert [json.loads(line) for line in download.text.splitlines()] == filtered["items"]
    assert download.headers["X-Exported-Log-Count"] == "1"
    assert "no-store" in download.headers["cache-control"]
    assert logs(client, headers, task_id, start="invalid").status_code == 400
    assert logs(client, headers, task_id, level="unknown").status_code == 400


def test_writer_redacts_before_storage_and_ignores_raw_payload(api):
    from api.monitoring.execution_logs import record_execution_event

    app, client, owner, headers, _, _ = api
    key = "owner-provider-value-123"
    response = client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "test", "api_key": key},
    )
    assert response.status_code == 201
    task_id, _ = seed(app, owner)
    with Session(app.state.monitor.task_engine) as db:
        record_execution_event(
            db.get(AsyncTask, task_id),
            "unit.failed",
            {
                "problem_id": key,
                "strategy": "password=secret",
                "status": "failed",
                "generated_code": "private code",
                "error_message": "private error",
                "current": 1,
            },
        )
    rows = logs(client, headers, task_id).json()["data"]["items"]
    assert len(rows) == 1 and rows[0]["level"] == "ERROR"
    payload = json.dumps(rows)
    assert key not in payload and "password=secret" not in payload and "private" not in payload
    with app.state.auth.store.connection() as db:
        raw = str([tuple(row) for row in db.execute("SELECT * FROM api_monitor_logs")])
    assert key not in raw and "password=secret" not in raw and "private code" not in raw


def test_logging_failure_does_not_change_task_or_leak_error(api, monkeypatch, caplog):
    from api.monitoring.store import MonitorStore

    app, _, owner, *_ = api
    task_id, _ = seed(app, owner)

    def fail(*args, **kwargs):
        raise RuntimeError("private-storage-credential")

    monkeypatch.setattr(MonitorStore, "append_log", fail)
    with Session(app.state.monitor.task_engine) as db:
        TaskManager(db).update_task_status(task_id, "completed")
        assert db.get(AsyncTask, task_id).status == "completed"
    assert "execution_log_write_failed" in caplog.text
    assert "private-storage-credential" not in caplog.text


def test_alias_does_not_fall_back_on_wrong_owner_or_broken_link(api):
    app, client, owner, headers, bob, other = api
    task_id, entity_id = seed(app, owner)
    app.state.files.store.register_run(entity_id, bob)
    assert logs(client, other, entity_id).status_code == 404
    with Session(app.state.monitor.task_engine) as db:
        db.get(AsyncTask, task_id).entity_id = str(uuid4())
        db.commit()
    assert logs(client, headers, entity_id).status_code == 404


@pytest.mark.parametrize("missing", [False, True])
def test_real_evaluation_worker_records_units(api, monkeypatch, tmp_path, missing):
    from test_celery_tasks import _seed_problem

    from src.harness import AlgorithmHarness
    from src.models import ExecutionResult
    from src.tasks.evaluation import run_evaluation_task

    app, client, owner, headers, *_ = api
    monkeypatch.chdir(tmp_path)
    task_id, entity_id = seed(app, owner)
    key = client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "worker", "api_key": "worker-private-key"},
    ).json()["data"]["id"]
    with Session(app.state.monitor.task_engine) as db:
        evaluation = db.get(Evaluation, entity_id)
        evaluation.api_key_id, evaluation.model = key, "test-model"
        evaluation.problem_ids = ["p1", "missing"] if missing else ["p1"]
        _seed_problem(db, "p1")
        db.commit()
    monkeypatch.setattr(
        "src.tasks.evaluation.get_db_session", lambda: Session(app.state.monitor.task_engine)
    )
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda **kwargs: None)
    monkeypatch.setattr("src.tasks.evaluation.publish_progress", lambda *args: False)
    monkeypatch.setattr(
        AlgorithmHarness, "_prepare_strategy_runtime", lambda *args: (object(), object())
    )
    monkeypatch.setattr(
        AlgorithmHarness,
        "_execute_problem",
        lambda self, strategy, problem, *args: ExecutionResult(
            problem_id=problem.problem_id,
            strategy=strategy.name,
            generated_code="private code",
            status="success",
            total_tokens=10,
            execution_time_seconds=0.01,
            difficulty="easy",
        ),
    )
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", lambda *args: (0.01, {}))
    run_evaluation_task.run(entity_id)
    response = logs(client, headers, task_id)
    assert response.status_code == 200, response.text
    rows = response.json()["data"]["items"]
    events = [row["message"] for row in rows]
    assert events.count("unit.started") == (2 if missing else 1)
    assert events.count("unit.completed") == 1
    assert events.count("unit.failed") == int(missing)
    assert "task.started" in events
    assert ("task.failed" if missing else "task.completed") in events
    assert "worker-private-key" not in json.dumps(rows) and "private code" not in json.dumps(rows)
    # A new store instance sees the worker writes; no process-local subscriber is involved.
    from api.auth.store import AuthStore
    from api.monitoring.store import MonitorStore

    store = MonitorStore(AuthStore(app.state.auth.settings.AUTH_DATABASE_PATH))
    assert store.query_logs(user_id=owner, run_id="async:" + task_id)[1] == len(rows)


def test_legacy_collision_is_separate_and_time_pagination_export_match(api):
    from datetime import datetime, timezone

    app, client, owner, headers, *_ = api
    task_id, _ = seed(app, owner)
    app.state.files.store.register_run(task_id, owner)
    app.state.monitor.store.append_log("INFO", "legacy-only", user_id=owner, run_id=task_id)
    with Session(app.state.monitor.task_engine) as db:
        manager = TaskManager(db)
        manager.update_task_status(task_id, "running")
        manager.update_task_status(task_id, "completed")
    rows = logs(client, headers, task_id).json()["data"]["items"]
    assert len(rows) == 2 and all(r["message"] != "legacy-only" for r in rows)
    start = datetime.fromtimestamp(min(r["timestamp"] for r in rows) - 1, timezone.utc).isoformat()
    end = datetime.fromtimestamp(max(r["timestamp"] for r in rows) + 1, timezone.utc).isoformat()
    page = logs(client, headers, task_id, start=start, end=end, limit=1, offset=1).json()["data"]
    assert page["total"] == 2 and len(page["items"]) == 1
    download = client.get(
        f"/api/v1/logs/download/{task_id}",
        headers=headers,
        params={"start": start, "end": end, "limit": 1, "offset": 1},
    )
    assert [json.loads(line) for line in download.text.splitlines()] == rows
    legacy = str(uuid4())
    app.state.files.store.register_run(legacy, owner)
    app.state.monitor.store.append_log("INFO", "old-run", user_id=owner, run_id=legacy)
    assert logs(client, headers, legacy).json()["data"]["items"][0]["message"] == "old-run"


@pytest.mark.parametrize("task_type", ["experiment", "benchmark", "import"])
def test_other_worker_entrypoints_emit_real_progress(api, monkeypatch, task_type):
    import importlib

    from api.db.models import BenchmarkRun, BenchmarkSuite, Experiment

    app, client, owner, headers, *_ = api
    task_id, entity_id = seed(app, owner, task_type)
    module = importlib.import_module(
        "src.tasks." + ("imports" if task_type == "import" else task_type)
    )
    monkeypatch.setattr(module, "get_db_session", lambda: Session(app.state.monitor.task_engine))
    if task_type == "import":

        def execute(job_id, user_id, on_progress, **kwargs):
            on_progress(1, 2)
            return {"status": "completed"}

        monkeypatch.setattr(module, "execute_import", execute)
    else:
        with Session(app.state.monitor.task_engine) as db:
            if task_type == "experiment":
                model = Experiment
                db.add(
                    Experiment(
                        id=entity_id, user_id=owner, name="log-test", config={}, status="pending"
                    )
                )
            else:
                model = BenchmarkRun
                suite_id = str(uuid4())
                db.add(BenchmarkSuite(id=suite_id, user_id=owner, name="log-test", problems=["p1"]))
                db.flush()
                db.add(
                    BenchmarkRun(
                        id=entity_id,
                        user_id=owner,
                        suite_id=suite_id,
                        model="test",
                        config={},
                        status="pending",
                    )
                )
            db.commit()

        def execute(entity_id, user_id):
            service = app.state.experiments if task_type == "experiment" else app.state.benchmarks
            service._write_progress(entity_id, user_id, 1, 2, "private provider message")
            with Session(app.state.monitor.task_engine) as db:
                db.get(model, entity_id).status = "completed"
                db.commit()

        monkeypatch.setattr(module, "execute_" + task_type, execute)
    result = getattr(module, "run_" + task_type + "_task").run(entity_id, owner)
    assert result["status"] == "completed"
    rows = logs(client, headers, task_id).json()["data"]["items"]
    assert [row["message"] for row in rows] == ["task.completed", "task.progress", "task.started"]
    assert rows[1]["context"]["current"] == 1 and rows[1]["context"]["total"] == 2
    assert "private" not in json.dumps(rows)


def test_independent_worker_process_events_persist(api):
    import subprocess
    import sys

    app, client, owner, headers, *_ = api
    task_id, _ = seed(app, owner)
    code = """
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from src.task_manager import TaskManager
engine = create_engine(sys.argv[1])
with Session(engine) as db:
    TaskManager(db).update_task_status(sys.argv[2], 'completed')
engine.dispose()
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(app.state.monitor.task_engine.url), task_id],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert logs(client, headers, task_id).json()["data"]["items"][0]["message"] == "task.completed"


def test_invalid_progress_cannot_smuggle_payload(api):
    app, client, owner, headers, *_ = api
    task_id, _ = seed(app, owner)
    with Session(app.state.monitor.task_engine) as db:
        TaskManager(db).update_task_progress(
            task_id,
            {
                "current": {"private": "body"},
                "total": "private code",
                "percentage": -1,
                "status": "private error",
                "message": "private prompt",
            },
            "running",
        )
    rows = logs(client, headers, task_id).json()["data"]["items"]
    assert len(rows) == 1 and "private" not in json.dumps(rows)
