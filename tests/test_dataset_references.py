"""Private imports -> immutable datasets -> three business execution paths (#308)."""

import json
import uuid
from pathlib import Path

import pytest
from pydantic import ValidationError
from test_api_experiment_benchmark import api as api_fixture
from test_api_experiment_benchmark import celery_submit as celery_submit
from test_api_files import problem, signup

api = api_fixture

from api.experiment_models import ABTestCreateRequest, BenchmarkRunRequest, ExperimentCreateRequest


def import_personal(client, headers, pid="private-1"):
    response = client.post(
        "/api/v1/problems/upload",
        headers=headers,
        files={
            "file": (
                "private.json",
                json.dumps(
                    [
                        problem(
                            pid, source_metadata={"batch": "original"}, source_problem_id="origin-1"
                        )
                    ]
                ),
                "application/json",
            )
        },
        data={"mode": "overwrite"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def payload(kind, key, source):
    common = {"api_key_id": key, **source}
    if kind == "experiment":
        return {**common, "models": [{"model": "test"}], "strategies": [{"name": "vanilla"}]}
    if kind == "ab":
        return {
            **common,
            "model": {"model": "test"},
            "strategy": {"name": "vanilla"},
            "prompt_variants": [{"id": "a"}, {"id": "b"}],
        }
    return {**common, "model": "test"}


def create(client, headers, key, kind, source):
    url = {"experiment": "/api/v1/experiments", "ab": "/api/v1/ab-tests"}.get(kind)
    if kind == "benchmark":
        suite = client.post(
            "/api/v1/benchmarks/suites",
            headers=headers,
            json={"name": f"private-suite-{uuid.uuid4()}", "problems": ["private-1"]},
        )
        assert suite.status_code == 201, suite.text
        url = f'/api/v1/benchmarks/suites/{suite.json()["data"]["id"]}/run'
    return client.post(url, headers=headers, json=payload(kind, key, source))


@pytest.mark.parametrize("kind", ["experiment", "benchmark", "ab"])
def test_import_reference_snapshot_execution_and_recovery(api, kind):  # noqa: F811
    client, headers, key, app = api
    assert client.get("/api/v1/datasets", headers=headers).json()["data"] == []
    imported = import_personal(client, headers)
    listed = client.get("/api/v1/datasets", headers=headers)
    assert listed.status_code == 200, listed.text
    ref = listed.json()["data"][0]
    assert ref["problem_count"] == 1
    response = create(client, headers, key, kind, {"dataset_id": ref["id"]})
    assert response.status_code in (201, 202), response.text
    view = response.json()["data"]
    assert "problems" not in json.dumps(view.get("config", {}).get("dataset_snapshot", {}))
    import_personal(client, headers, "replacement")
    # Destroy the entire mutable collection and upload files, as expiry/cleanup would.
    with app.state.files.store.connection() as db:
        db.execute("DELETE FROM api_file_datasets")
    for raw in app.state.files.settings.UPLOAD_DIR.rglob("*.json"):
        raw.unlink()
    from api.datasets import execution_dataset
    from api.db.models import ABTest, BenchmarkRun, Experiment

    service = {
        "experiment": app.state.experiments,
        "benchmark": app.state.benchmarks,
        "ab": app.state.ab_tests,
    }[kind]
    model = {"experiment": Experiment, "benchmark": BenchmarkRun, "ab": ABTest}[kind]
    with service._session() as session:
        row = session.get(model, view["id"])
        owner = row.user_id
        config = dict(row.config)
    for _ in range(2):
        with execution_dataset(config, owner) as path:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            assert data[0]["problem_id"] == "private-1"
            assert data[0]["tags"] == ["array"]
            assert data[0]["difficulty"] == "easy"
            assert data[0]["source_metadata"] == {"batch": "original"}
            assert data[0]["source_problem_id"] == "origin-1"
            assert data[0]["judge_config"]
        assert not Path(path).exists()
    seen = []
    paths = []

    def pause_first_attempt():
        if len(seen) == 1:
            with service._session() as session:
                task = session.scalar(select(AsyncTask).where(AsyncTask.entity_id == view["id"]))
                TaskManager(session).pause_task(task.id, owner)

    from sqlalchemy import select

    from api.db.models import AsyncTask
    from src.task_manager import TaskManager

    class Runner:
        def __init__(self, *args):
            self.config = args[-1]

        def run(self):
            seen.append(json.loads(Path(self.config.dataset_path).read_text(encoding="utf-8")))
            paths.append(self.config.dataset_path)
            pause_first_attempt()
            self.paused = len(seen) == 1
            return Path(self.config.output_dir)

        def execute(self):
            seen.append(json.loads(Path(self.config.dataset_path).read_text(encoding="utf-8")))
            paths.append(self.config.dataset_path)
            pause_first_attempt()
            self.paused = len(seen) == 1
            return {"accuracy": 1.0, "cost_usd": 0.0}

    if kind == "benchmark":
        service._executor_factory = Runner
    else:
        service._runner_factory = Runner
        url = "/api/v1/experiments" if kind == "experiment" else "/api/v1/ab-tests"
        started = client.post(f'{url}/{view["id"]}/run', headers=headers)
        assert started.status_code == 202, started.text

    def execute_attempt(executor):
        # The experiment Celery wrapper claims before invoking the service.
        if kind == "experiment":
            with executor._session() as session:
                task = session.scalar(select(AsyncTask).where(AsyncTask.entity_id == view["id"]))
                TaskManager(session).claim_task(task.id, task.celery_task_id)
        executor._execute(view["id"], owner)
        # Benchmark/experiment wrappers acknowledge cooperative stop on exit.
        with executor._session() as session:
            task = session.scalar(select(AsyncTask).where(AsyncTask.entity_id == view["id"]))
            TaskManager(session, celery_task_id=task.celery_task_id).confirm_stopped(task.id)

    execute_attempt(service)
    with service._session() as session:
        assert session.get(model, view["id"]).status == "paused"
        task = session.scalar(select(AsyncTask).where(AsyncTask.entity_id == view["id"]))
        TaskManager(session).resume_task(task.id, owner)
    assert all(not Path(path).exists() for path in paths)
    # A fresh worker service must consume the database snapshot without uploads.
    options = {"executor_factory" if kind == "benchmark" else "runner_factory": Runner}
    restarted = type(service)(auth=app.state.auth, recover=False, **options)
    try:
        execute_attempt(restarted)
        assert len(seen) == 2 and seen[0] == seen[1]
        assert seen[0][0]["problem_id"] == "private-1"
        assert all(not Path(path).exists() for path in paths)
        with restarted._session() as session:
            assert session.get(model, view["id"]).status == "completed"
    finally:
        restarted._engine.dispose()


@pytest.mark.parametrize("kind", ["experiment", "benchmark", "ab"])
def test_reference_ownership_unknown_empty_and_conflict(api, kind):  # noqa: F811
    client, headers, key, app = api
    import_personal(client, headers)
    ref = client.get("/api/v1/datasets", headers=headers).json()["data"][0]["id"]
    bob = signup(client, "bob")
    bob_headers = {"Authorization": "Bearer " + bob["access_token"]}
    assert client.get("/api/v1/datasets", headers=bob_headers).json()["data"] == []
    bob_key = client.post(
        "/api/v1/api-keys",
        headers=bob_headers,
        json={"provider": "openai", "key_name": "bob", "api_key": "fake"},
    ).json()["data"]["id"]
    assert create(client, bob_headers, bob_key, kind, {"dataset_id": ref}).status_code == 404
    assert create(client, headers, key, kind, {"dataset_id": "unknown"}).status_code == 404
    assert (
        create(
            client, headers, key, kind, {"dataset_id": ref, "dataset_path": "problems.json"}
        ).status_code
        == 400
    )
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_datasets SET payload='[]'")
    response = create(client, headers, key, kind, {"dataset_id": ref})
    assert response.status_code == 400, response.text
    assert "empty" in response.text.lower()


@pytest.mark.parametrize(
    "kind,model",
    [
        ("experiment", ExperimentCreateRequest),
        ("benchmark", BenchmarkRunRequest),
        ("ab", ABTestCreateRequest),
    ],
)
@pytest.mark.parametrize(
    "source",
    [{}, {"dataset_id": ""}, {"dataset_path": " "}, {"dataset_id": "x", "dataset_path": "p"}],
)
def test_source_contract(kind, model, source):
    with pytest.raises(ValidationError):
        model(**payload(kind, "key", source))


@pytest.mark.parametrize("kind", ["experiment", "benchmark", "ab"])
def test_legacy_path_snapshot_survives_source_removal(
    api, tmp_path, monkeypatch, kind
):  # noqa: F811
    from api.config import settings
    from api.datasets import execution_dataset
    from api.db.models import ABTest, BenchmarkRun, Experiment

    client, headers, key, app = api
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    source = tmp_path / "legacy.json"
    source.write_text(json.dumps([problem("legacy-1")]), encoding="utf-8")
    response = create(client, headers, key, kind, {"dataset_path": "legacy.json"})
    assert response.status_code in (201, 202), response.text
    service, model = {
        "experiment": (app.state.experiments, Experiment),
        "benchmark": (app.state.benchmarks, BenchmarkRun),
        "ab": (app.state.ab_tests, ABTest),
    }[kind]
    with service._session() as session:
        row = session.get(model, response.json()["data"]["id"])
        config, owner = dict(row.config), row.user_id
    source.unlink()
    with execution_dataset(config, owner) as path:
        assert json.loads(Path(path).read_text(encoding="utf-8"))[0]["problem_id"] == "legacy-1"
    assert create(client, headers, key, kind, {"dataset_path": "../secret.json"}).status_code == 400


def test_snapshot_rejects_wrong_owner_tampering_and_cleans_failed_attempt(api):  # noqa: F811
    from copy import deepcopy

    from api.datasets import execution_dataset
    from api.db.models import Experiment

    client, headers, key, app = api
    import_personal(client, headers)
    ref = client.get("/api/v1/datasets", headers=headers).json()["data"][0]["id"]
    response = create(client, headers, key, "experiment", {"dataset_id": ref})
    with app.state.experiments._session() as session:
        row = session.get(Experiment, response.json()["data"]["id"])
        config, owner = dict(row.config), row.user_id
    with pytest.raises(ValueError, match="owner"):
        with execution_dataset(config, "another-user"):
            pytest.fail("Cross-owner snapshot was consumed")
    changed = deepcopy(config)
    changed["dataset_snapshot"]["problems"][0]["tags"] = ["changed"]
    with pytest.raises(ValueError, match="integrity"):
        with execution_dataset(changed, owner):
            pytest.fail("Corrupt snapshot was consumed")
    with pytest.raises(RuntimeError, match="runner failed"):
        with execution_dataset(config, owner) as path:
            assert Path(path).is_file()
            raise RuntimeError("runner failed")
    assert not Path(path).exists()
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_datasets SET payload='broken'")
    assert create(client, headers, key, "experiment", {"dataset_id": ref}).status_code == 400
    # Deleting an unqueued business row removes its co-located snapshot.
    deleted = client.delete(f'/api/v1/experiments/{response.json()["data"]["id"]}', headers=headers)
    assert deleted.status_code == 204
    with app.state.experiments._session() as session:
        assert session.get(Experiment, response.json()["data"]["id"]) is None
