"""Durable artifact publication contracts; no online model calls."""

from __future__ import annotations

import uuid

from sqlalchemy import inspect, text

from api.db.engine import make_engine, make_session_factory
from api.db.migrate import downgrade, offline_upgrade_sql, upgrade
from api.db.models import Base, Evaluation, EvaluationResult
from src.task_service import TaskUnit
from src.tasks.evaluation import _record_unit_result


def test_publication_migration_preserves_legacy_rows_and_is_reversible(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'migration.sqlite3'}")
    try:
        upgrade(engine, "0005")
        with engine.begin() as db:
            db.execute(
                text(
                    "INSERT INTO evaluations (id,user_id,status,strategy_names,problem_ids,problem_count,spent_usd,completed_count,failed_count,created_at,updated_at) VALUES ('legacy','owner','completed','[\"vanilla\"]','[\"p1\"]',1,0,1,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
            db.execute(
                text(
                    "INSERT INTO evaluation_results (id,evaluation_id,problem_id,strategy_name,status,created_at,updated_at) VALUES ('result','legacy','p1','vanilla','success',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
                )
            )
        upgrade(engine)
        assert "evaluation_artifact_publications" in inspect(engine).get_table_names()
        assert "execution_payload" in {
            c["name"] for c in inspect(engine).get_columns("evaluation_results")
        }
        with engine.connect() as db:
            assert (
                db.execute(
                    text("SELECT execution_payload FROM evaluation_results WHERE id='result'")
                ).scalar()
                is None
            )
        downgrade(engine, "0005")
        assert "evaluation_artifact_publications" not in inspect(engine).get_table_names()
        with engine.connect() as db:
            assert (
                db.execute(text("SELECT status FROM evaluation_results WHERE id='result'")).scalar()
                == "success"
            )
    finally:
        engine.dispose()


def test_publication_migration_renders_postgresql_without_server():
    sql = offline_upgrade_sql("postgresql://offline:offline@localhost/offline")
    assert "CREATE TABLE evaluation_artifact_publications" in sql
    assert "execution_payload JSON" in sql


def test_worker_retains_real_execution_payload_without_retaining_credentials(tmp_path):
    engine = make_engine(f"sqlite:///{tmp_path / 'results.sqlite3'}")
    Base.metadata.create_all(engine)
    session = make_session_factory(engine)
    try:
        with session() as db:
            evaluation = Evaluation(
                id=str(uuid.uuid4()),
                user_id="owner",
                status="running",
                strategy_names=["vanilla"],
                problem_ids=["p1"],
                problem_count=1,
            )
            db.add(evaluation)
            db.flush()
            data = {
                "problem_id": "p1",
                "status": "success",
                "strategy_name": "vanilla",
                "iterations": [],
                "total_tokens": 37,
                "metadata": {
                    "api_key": "fake-private-value",
                    "cost_unknown": True,
                    "problem_snapshot": {"tags": [], "origin": "personal"},
                },
            }
            _record_unit_result(
                db,
                evaluation,
                TaskUnit(
                    unit_id="unit",
                    strategy="vanilla",
                    problem_id="p1",
                    status="completed",
                    result=data,
                ),
            )
            db.commit()
            row = db.query(EvaluationResult).one()
            assert row.execution_payload["total_tokens"] == 37
            assert row.execution_payload["metadata"]["api_key"] != "fake-private-value"
            assert row.execution_payload["metadata"]["cost_unknown"] is True
    finally:
        engine.dispose()


import secrets
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.files.config import FileSettings
from api.main import create_app
from tests.test_api_files import auth_headers, new_task, signup


@pytest.fixture
def artifact_env(tmp_path):
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=1000,
        AUTH_PROTECTED_RATE_LIMIT=1000,
    )
    files = FileSettings(
        _env_file=None, UPLOAD_DIR=tmp_path / "uploads", FILE_MAX_USER_BYTES=4 * 1024 * 1024
    )
    app = create_app(auth, files)
    with TestClient(app) as client, patch("src.task_manager.celery_app.send_task"):
        alice, bob = signup(client, "alice"), signup(client, "bob")
        evaluation_id = new_task(client, alice)
        from api.services.artifact_service import EvaluationArtifactService, stage_publication

        service = EvaluationArtifactService(app.state.task_session_factory, app.state.files)
        owner = client.get("/api/v1/users/me", headers=auth_headers(alice)).json()["data"]["id"]

        def stage(status="completed", count=1, raw=None):
            with app.state.task_session_factory() as db:
                evaluation = db.get(Evaluation, evaluation_id)
                evaluation.status = status
                evaluation.problem_ids = [f"p{i+1}" for i in range(count)]
                row = db.query(EvaluationResult).filter_by(evaluation_id=evaluation_id).first()
                if row is None:
                    row = EvaluationResult(
                        id=str(uuid.uuid4()),
                        evaluation_id=evaluation_id,
                        problem_id="p1",
                        strategy_name="vanilla",
                        status="success",
                        metrics={
                            "total_tokens": 37,
                            "cost_unknown": True,
                            "problem_snapshot": {"origin": "personal", "tags": []},
                        },
                    )
                    db.add(row)
                row.execution_payload = raw
                pub = stage_publication(db, evaluation)
                db.commit()
                return pub.revision

        yield {
            "client": client,
            "alice": alice,
            "bob": bob,
            "app": app,
            "files": app.state.files,
            "service": service,
            "id": evaluation_id,
            "owner": owner,
            "stage": stage,
        }


def test_durable_snapshot_is_truthful_idempotent_and_independently_publishable(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    assert e["stage"]() == revision
    result = e["service"].publish(e["id"], e["owner"], revision)
    assert result["available"] and result["status"] == "published"
    payload = __import__("json").loads(e["files"].export_results(e["id"], e["owner"], "json")[2])
    assert payload["complete"] is True and payload["recorded_units"] == 1
    row = payload["results"]["vanilla"][0]
    assert row["execution"] is None and row["metrics"]["cost_unknown"] is True
    assert row["metrics"]["problem_snapshot"]["origin"] == "personal"
    assert "code" not in row and "cost_usd" not in row["metrics"]


def test_partial_newer_revision_cannot_be_replaced_by_older_publication(artifact_env):
    e = artifact_env
    first = e["stage"]()
    e["service"].publish(e["id"], e["owner"], first)
    later = e["stage"]("paused", 2)
    assert later > first
    assert not e["service"].state(e["id"], e["owner"])["available"]
    e["service"].publish(e["id"], e["owner"], later)
    file_id = e["files"].store.result_file(e["id"], e["owner"])["id"]
    e["service"].publish(e["id"], e["owner"], first)
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == file_id
    payload = __import__("json").loads(e["files"].export_results(e["id"], e["owner"], "json")[2])
    assert (
        not payload["complete"]
        and payload["expected_units"] == 2
        and payload["recorded_units"] == 1
    )


def test_file_failure_preserves_execution_and_can_retry_without_model(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    with patch.object(e["files"], "_persist", side_effect=OSError("private-path must not leak")):
        result = e["service"].publish(e["id"], e["owner"], revision)
    assert result["status"] == "failed" and result["error_code"] == "storage_error"
    assert "private-path" not in str(result)
    with e["app"].state.task_session_factory() as db:
        assert db.get(Evaluation, e["id"]).status == "completed"
        assert db.query(EvaluationResult).count() == 1
    assert e["service"].publish(e["id"], e["owner"], revision)["available"]


def test_activation_before_business_confirmation_is_recoverable_and_idempotent(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    with patch.object(e["service"], "_mark_published", side_effect=OSError("commit boundary")):
        assert e["service"].publish(e["id"], e["owner"], revision)["status"] == "failed"
    before = e["files"].store.result_file(e["id"], e["owner"])["id"]
    assert e["service"].publish(e["id"], e["owner"], revision)["available"]
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == before
    with e["files"].store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM api_file_objects WHERE category='results'").fetchone()[
                0
            ]
            == 1
        )


def test_active_artifact_deletion_is_not_undone_by_late_publication_or_retry(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    e["service"].publish(e["id"], e["owner"], revision)
    e["files"].delete_file(e["files"].store.result_file(e["id"], e["owner"])["id"], e["owner"])
    assert not e["service"].publish(e["id"], e["owner"], revision)["available"]
    with pytest.raises(HTTPException) as error:
        e["service"].retry(e["id"], e["owner"])
    assert error.value.status_code == 409
    with e["files"].store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM api_file_objects WHERE category='results'").fetchone()[
                0
            ]
            == 0
        )


def test_replacement_obeys_coexisting_storage_quota_and_cleans_failed_candidates(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    e["service"].publish(e["id"], e["owner"], revision)
    old = e["files"].store.result_file(e["id"], e["owner"])
    later = e["stage"]("paused", 2)
    e["files"].settings.FILE_MAX_USER_BYTES = old["size"] + 1
    result = e["service"].publish(e["id"], e["owner"], later)
    assert result["error_code"] == "storage_limit" and not result["available"]
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == old["id"]
    e["files"].settings.FILE_MAX_USER_BYTES = 4 * 1024 * 1024
    assert e["service"].publish(e["id"], e["owner"], later)["available"]
    with e["files"].store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM api_file_objects WHERE category='results'").fetchone()[
                0
            ]
            == 1
        )


def test_committed_candidate_is_reused_after_process_loss_even_at_quota(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    from api.db.models import EvaluationArtifactPublication

    with e["app"].state.task_session_factory() as db:
        snapshot = db.get(EvaluationArtifactPublication, e["id"]).snapshot
    candidate = e["files"].stage_snapshot(e["id"], e["owner"], snapshot)
    e["files"].settings.FILE_MAX_USER_BYTES = candidate["size"] + 1
    assert e["service"].publish(e["id"], e["owner"], revision)["available"]
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == candidate["id"]


def test_losing_publisher_failure_does_not_downgrade_concurrent_success(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    original = e["files"].stage_snapshot

    def racing_stage(*args, **kwargs):
        with patch.object(e["files"], "stage_snapshot", original):
            assert e["service"].publish(e["id"], e["owner"], revision)["available"]
        raise OSError("losing publisher")

    with patch.object(e["files"], "stage_snapshot", side_effect=racing_stage):
        state = e["service"].publish(e["id"], e["owner"], revision)
    assert state["available"] and state["status"] == "published"


@pytest.mark.parametrize("kind", ["json", "csv", "markdown", "html", "png", "zip"])
def test_versioned_http_downloads_include_real_revision_and_completeness(artifact_env, kind):
    e = artifact_env
    revision = e["stage"]("paused", 2)
    e["service"].publish(e["id"], e["owner"], revision)
    response = e["client"].get(
        f"/api/v1/results/{e['id']}/download?format={kind}", headers=auth_headers(e["alice"])
    )
    assert response.status_code == 200, (
        response.text[:100] if kind not in {"png", "zip"} else response.status_code
    )
    assert response.headers["x-artifact-revision"] == str(revision)
    assert response.headers["x-artifact-completeness"] == "partial"
    browser_response = e["client"].get(
        f"/api/v1/results/{e['id']}/download?format={kind}",
        headers={**auth_headers(e["alice"]), "Origin": "http://localhost:3000"},
    )
    assert (
        "x-artifact-revision"
        in browser_response.headers.get("access-control-expose-headers", "").lower()
    )
    assert (
        "x-artifact-completeness"
        in browser_response.headers.get("access-control-expose-headers", "").lower()
    )
    if kind == "json":
        assert response.json()["results"]["vanilla"][0]["metrics"]["cost_unknown"] is True
    elif kind == "csv":
        import csv
        import io

        rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
        assert rows[0]["complete"] == "false" and rows[0]["execution"] == ""
    elif kind == "png":
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    elif kind == "zip":
        import io
        import json
        import zipfile

        with zipfile.ZipFile(io.BytesIO(response.content)) as bundle:
            assert {
                "results.json",
                "results.csv",
                "report.md",
                "report.html",
                "success-rate.png",
            } == set(bundle.namelist())
            assert json.loads(bundle.read("results.json"))["complete"] is False
    else:
        assert "Partial evaluation results" in response.text


def test_publication_http_owner_retry_queue_failure_and_empty_semantics(artifact_env):
    e = artifact_env
    url = f"/api/v1/results/{e['id']}/publication"
    assert (
        e["client"].get(url, headers=auth_headers(e["alice"])).json()["data"]["error_code"]
        == "no_results"
    )
    assert e["client"].post(url + "/retry", headers=auth_headers(e["alice"])).status_code == 409
    assert e["client"].get(url, headers=auth_headers(e["bob"])).status_code == 404
    assert e["client"].post(url + "/retry", headers=auth_headers(e["bob"])).status_code == 404
    e["stage"]()
    with patch.object(
        e["app"].state.artifacts, "_enqueue", side_effect=OSError("broker private URI")
    ):
        response = e["client"].post(url + "/retry", headers=auth_headers(e["alice"]))
    assert response.status_code == 503
    state = e["client"].get(url, headers=auth_headers(e["alice"])).json()["data"]
    assert state["error_code"] == "queue_unavailable" and not state["available"]
    assert "private URI" not in response.text
    with patch.object(
        e["app"].state.artifacts,
        "_enqueue",
        side_effect=lambda eid, owner, rev, manual: e["service"].publish(eid, owner, rev, manual),
    ):
        assert (
            e["client"]
            .post(url + "/retry", headers=auth_headers(e["alice"]))
            .json()["data"]["available"]
        )


@pytest.fixture
def worker_env(artifact_env, monkeypatch, tmp_path):
    e = artifact_env
    from api.db.models import AsyncTask, Problem
    from src.harness import AlgorithmHarness
    from src.models import ExecutionResult
    from src.tasks.evaluation import run_evaluation_task

    factory = e["app"].state.task_session_factory
    with factory() as db:
        evaluation = db.get(Evaluation, e["id"])
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="generation-1",
            task_type="evaluation",
            entity_id=e["id"],
            user_id=e["owner"],
            status="pending",
        )
        db.add(task)
        db.flush()
        evaluation.async_task_id = task.id
        db.add(
            Problem(
                id=str(uuid.uuid4()),
                problem_id="p1",
                title="Echo",
                description="Return the integer x unchanged.",
                difficulty="easy",
                tags=["array"],
                test_cases=[{"input": {"x": 1}, "expected_output": 1}],
            )
        )
        db.commit()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("api.auth.config.AuthSettings", lambda: e["app"].state.auth.settings)
    monkeypatch.setattr("api.auth.service.AuthService", lambda *a: e["app"].state.auth)
    monkeypatch.setattr("src.tasks.evaluation.get_db_session", factory)
    monkeypatch.setattr(
        "src.tasks.evaluation.get_artifact_service", lambda db: e["service"], raising=False
    )
    monkeypatch.setattr("src.tasks.evaluation.publish_progress", lambda *a, **k: None)
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda **k: None)
    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", lambda *a: (None, None))
    calls = []

    def execute(self, config, problem, *args):
        calls.append(problem.problem_id)
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=config.name,
            generated_code="def solve(x): return x",
            status="success",
            total_tokens=37,
            difficulty="easy",
        )

    monkeypatch.setattr(AlgorithmHarness, "_execute_problem", execute)
    monkeypatch.setattr(
        AlgorithmHarness, "_estimate_cost", lambda *a: (0.0, {"unknown_pricing": True})
    )
    return e, calls, run_evaluation_task


def test_real_worker_commits_publishes_and_http_downloads_without_manual_injection(worker_env):
    e, calls, run_evaluation_task = worker_env
    assert run_evaluation_task.run(e["id"])["status"] == "completed"
    response = e["client"].get(
        f"/api/v1/results/{e['id']}/download", headers=auth_headers(e["alice"])
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["complete"] is True
    actual = payload["results"]["vanilla"][0]
    assert actual["execution"]["generated_code"] == "def solve(x): return x"
    assert actual["execution"]["total_tokens"] == 37
    assert actual["metrics"]["cost_unknown"] is True
    first = e["files"].store.result_file(e["id"], e["owner"])["id"]
    assert run_evaluation_task.run(e["id"])["status"] == "completed"
    assert calls == ["p1"]
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == first


def test_expired_artifact_requires_explicit_retry_and_preserves_result_retention(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    e["service"].publish(e["id"], e["owner"], revision)
    before = e["files"].store.result_file(e["id"], e["owner"])
    assert before["expires_at"] is None
    with e["files"].store.connection() as db:
        db.execute("UPDATE api_file_objects SET expires_at=0 WHERE id=?", (before["id"],))
    assert not e["service"].publish(e["id"], e["owner"], revision)["available"]
    assert e["service"].publish(e["id"], e["owner"], revision, manual=True)["available"]
    after = e["files"].store.result_file(e["id"], e["owner"])
    assert after["id"] != before["id"] and after["expires_at"] is None


def test_corrupted_current_artifact_can_be_explicitly_rebuilt_from_committed_snapshot(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    e["service"].publish(e["id"], e["owner"], revision)
    before = e["files"].store.result_file(e["id"], e["owner"])
    e["files"].path(before["relative_path"], e["owner"]).write_bytes(b"corrupted")
    assert not e["service"].state(e["id"], e["owner"])["available"]
    assert e["service"].publish(e["id"], e["owner"], revision, manual=True)["available"]
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] != before["id"]


@pytest.mark.parametrize("ending", ["pause_resume", "cancel", "failure"])
def test_worker_partial_lifecycle_and_old_generation_preserve_current_artifacts(
    worker_env, monkeypatch, ending
):
    e, calls, worker = worker_env
    from api.db.models import AsyncTask, Problem
    from src.harness import AlgorithmHarness
    from src.tasks.evaluation import _publish_committed_artifacts

    factory = e["app"].state.task_session_factory
    with factory() as db:
        evaluation = db.get(Evaluation, e["id"])
        evaluation.problem_ids = ["p1", "p2"]
        evaluation.problem_count = 2
        if ending == "pause_resume":
            evaluation.budget_cap_usd = 0.05
        db.add(
            Problem(
                id=str(uuid.uuid4()),
                problem_id="p2",
                title="Echo 2",
                description="Return the integer x unchanged.",
                difficulty="easy",
                tags=["array"],
                test_cases=[{"input": {"x": 2}, "expected_output": 2}],
            )
        )
        db.commit()
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", lambda *a: (0.1, {}))
    if ending == "cancel":
        original = AlgorithmHarness._execute_problem

        def cancel(*args, **kwargs):
            result = original(*args, **kwargs)
            with factory() as db:
                evaluation = db.get(Evaluation, e["id"])
                evaluation.status = "cancelled"
                db.get(AsyncTask, evaluation.async_task_id).status = "cancelled"
                db.commit()
            return result

        monkeypatch.setattr(AlgorithmHarness, "_execute_problem", cancel)
    elif ending == "failure":
        original = _record_unit_result

        def fail_second(db, evaluation, unit):
            if unit.problem_id == "p2":
                raise RuntimeError("controlled callback failure")
            return original(db, evaluation, unit)

        monkeypatch.setattr("src.tasks.evaluation._record_unit_result", fail_second)
    if ending == "failure":
        with pytest.raises(RuntimeError, match="controlled callback failure"):
            worker.run(e["id"])
    else:
        assert worker.run(e["id"])["status"] == (
            "paused" if ending == "pause_resume" else "cancelled"
        )
    response = e["client"].get(
        f"/api/v1/results/{e['id']}/download", headers=auth_headers(e["alice"])
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert (
        not payload["complete"]
        and payload["expected_units"] == 2
        and payload["recorded_units"] == 1
    )
    assert (
        payload["state"]
        == {"pause_resume": "paused", "cancel": "cancelled", "failure": "failed"}[ending]
    )
    if ending == "pause_resume":
        previous = payload["revision"]
        with factory() as db:
            evaluation = db.get(Evaluation, e["id"])
            evaluation.budget_cap_usd = 1
            evaluation.status = "pending"
            task = db.get(AsyncTask, evaluation.async_task_id)
            task.status = "pending"
            task.celery_task_id = "generation-2"
            db.commit()
        assert worker.run(e["id"])["status"] == "completed"
        current = (
            e["client"]
            .get(f"/api/v1/results/{e['id']}/download", headers=auth_headers(e["alice"]))
            .json()
        )
        assert (
            current["complete"]
            and current["recorded_units"] == 2
            and current["revision"] > previous
        )
        assert calls == ["p1", "p2"]
        file_id = e["files"].store.result_file(e["id"], e["owner"])["id"]
        with factory() as db:
            _publish_committed_artifacts(db, e["id"], e["owner"], "generation-1")
        assert e["files"].store.result_file(e["id"], e["owner"])["id"] == file_id


def test_independent_retry_task_uses_only_snapshot_and_retries_transient_storage_errors(
    artifact_env, monkeypatch
):
    e = artifact_env
    revision = e["stage"]()
    from celery.exceptions import Retry

    from src.tasks.artifacts import publish_evaluation_artifacts

    monkeypatch.setattr("src.tasks.artifacts.get_db_session", e["app"].state.task_session_factory)
    monkeypatch.setattr("src.tasks.artifacts.get_artifact_service", lambda db: e["service"])
    with patch.object(e["files"], "_persist", side_effect=OSError("disk")):
        with patch.object(publish_evaluation_artifacts, "retry", side_effect=Retry()) as retry:
            with pytest.raises(Retry):
                publish_evaluation_artifacts.run(e["id"], e["owner"], revision)
            assert retry.call_args.kwargs["countdown"] == 10
    assert publish_evaluation_artifacts.run(e["id"], e["owner"], revision)["available"]


def test_publication_retry_cookie_requests_require_csrf(artifact_env):
    e = artifact_env
    e["stage"]()
    response = e["client"].post(
        "/api/v1/auth/login", json={"username": "alice", "password": "long-file-service-password!"}
    )
    assert response.status_code == 200
    url = f"/api/v1/results/{e['id']}/publication/retry"
    assert e["client"].post(url).status_code == 403
    with patch.object(e["app"].state.artifacts, "_enqueue"):
        assert (
            e["client"]
            .post(url, headers={"X-CSRF-Token": response.headers["x-csrf-token"]})
            .status_code
            == 202
        )


def test_late_inflight_older_snapshot_cannot_replace_newer_activation(artifact_env):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    e = artifact_env
    first = e["stage"]()
    staged = threading.Event()
    release = threading.Event()
    original = e["files"].stage_snapshot

    def pause_old(evaluation_id, owner, snapshot):
        metadata = original(evaluation_id, owner, snapshot)
        if snapshot["revision"] == first:
            staged.set()
            assert release.wait(10)
        return metadata

    with (
        patch.object(e["files"], "stage_snapshot", side_effect=pause_old),
        ThreadPoolExecutor(max_workers=1) as executor,
    ):
        old = executor.submit(e["service"].publish, e["id"], e["owner"], first)
        try:
            assert staged.wait(10)
            latest = e["stage"]("paused", 2)
            assert e["service"].publish(e["id"], e["owner"], latest)["available"]
            active = e["files"].store.result_file(e["id"], e["owner"])["id"]
        finally:
            release.set()
        assert old.result(timeout=10)["revision"] == latest
    assert e["files"].store.result_file(e["id"], e["owner"])["id"] == active
    with e["files"].store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM api_file_objects WHERE category='results'").fetchone()[
                0
            ]
            == 1
        )


def test_simultaneous_duplicate_publishers_leave_one_active_file(artifact_env):
    from concurrent.futures import ThreadPoolExecutor

    e = artifact_env
    revision = e["stage"]()
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(lambda _: e["service"].publish(e["id"], e["owner"], revision), range(2))
        )
    assert all(state["available"] for state in results)
    with e["files"].store.connection() as db:
        assert (
            db.execute("SELECT COUNT(*) FROM api_file_objects WHERE category='results'").fetchone()[
                0
            ]
            == 1
        )


def test_deleted_evaluation_rejects_delayed_publisher_and_removes_publication(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    assert e["service"].publish(e["id"], e["owner"], revision)["available"]
    assert (
        e["client"]
        .delete(f"/api/v1/evaluations/{e['id']}", headers=auth_headers(e["alice"]))
        .status_code
        == 204
    )
    with pytest.raises(HTTPException) as error:
        e["service"].publish(e["id"], e["owner"], revision)
    assert error.value.status_code == 404
    from api.db.models import EvaluationArtifactPublication

    with e["app"].state.task_session_factory() as db:
        assert db.get(EvaluationArtifactPublication, e["id"]) is None
    with e["files"].store.connection() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM api_file_objects WHERE run_id=?", (e["id"],)
            ).fetchone()[0]
            == 0
        )


def test_explicit_legacy_retry_builds_snapshot_from_actual_rows_only(artifact_env):
    e = artifact_env
    with e["app"].state.task_session_factory() as db:
        evaluation = db.get(Evaluation, e["id"])
        evaluation.status = "completed"
        db.add(
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id=e["id"],
                problem_id="p1",
                strategy_name="vanilla",
                status="failed",
                metrics=None,
                error_message="old failure",
            )
        )
        db.commit()
    assert e["service"].state(e["id"], e["owner"])["revision"] == 0
    with patch.object(
        e["service"],
        "_enqueue",
        side_effect=lambda eid, owner, rev, manual: e["service"].publish(eid, owner, rev, manual),
    ):
        state = e["service"].retry(e["id"], e["owner"])
    assert state["available"]
    payload = __import__("json").loads(e["files"].export_results(e["id"], e["owner"], "json")[2])
    actual = payload["results"]["vanilla"][0]
    assert (
        actual["status"] == "failed" and actual["metrics"] is None and actual["execution"] is None
    )


def test_lifecycle_only_revision_does_not_restore_deleted_result_content(artifact_env):
    e = artifact_env
    first = e["stage"]()
    e["service"].publish(e["id"], e["owner"], first)
    e["files"].delete_file(e["files"].store.result_file(e["id"], e["owner"])["id"], e["owner"])
    later = e["stage"]("running")
    assert later > first
    assert not e["service"].publish(e["id"], e["owner"], later)["available"]
    with e["app"].state.task_session_factory() as db:
        evaluation = db.get(Evaluation, e["id"])
        evaluation.problem_ids = ["p1", "p2"]
        evaluation.status = "completed"
        db.add(
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id=e["id"],
                problem_id="p2",
                strategy_name="vanilla",
                status="success",
                metrics={"total_tokens": 11},
            )
        )
        from api.services.artifact_service import stage_publication

        pub = stage_publication(db, evaluation)
        new = pub.revision
        db.commit()
    assert e["service"].publish(e["id"], e["owner"], new)["available"]


@pytest.mark.parametrize("queue_fails", [False, True])
def test_worker_file_failure_keeps_completed_results_and_records_retry_transport(
    worker_env, queue_fails
):
    e, calls, worker = worker_env
    with patch.object(
        e["service"],
        "_enqueue",
        side_effect=OSError("controlled queue failure") if queue_fails else None,
    ) as enqueue:
        with patch.object(e["files"], "_persist", side_effect=OSError("controlled disk failure")):
            assert worker.run(e["id"])["status"] == "completed"
        assert enqueue.called
    state = e["service"].state(e["id"], e["owner"])
    assert not state["available"] and state["error_code"] == (
        "queue_unavailable" if queue_fails else "storage_error"
    )
    assert calls == ["p1"]
    with e["app"].state.task_session_factory() as db:
        assert db.get(Evaluation, e["id"]).status == "completed"
        assert db.query(EvaluationResult).filter_by(evaluation_id=e["id"]).count() == 1
    assert e["service"].publish(e["id"], e["owner"], state["revision"], manual=True)["available"]
    assert calls == ["p1"]


def test_deleted_evaluation_independent_message_returns_unavailable(artifact_env, monkeypatch):
    e = artifact_env
    revision = e["stage"]()
    from src.tasks.artifacts import publish_evaluation_artifacts

    monkeypatch.setattr("src.tasks.artifacts.get_db_session", e["app"].state.task_session_factory)
    monkeypatch.setattr("src.tasks.artifacts.get_artifact_service", lambda db: e["service"])
    assert (
        e["client"]
        .delete(f"/api/v1/evaluations/{e['id']}", headers=auth_headers(e["alice"]))
        .status_code
        == 204
    )
    state = publish_evaluation_artifacts.run(e["id"], e["owner"], revision)
    assert not state["available"] and state["error_code"] == "result_not_found"


def test_late_unavailable_failure_cannot_overwrite_manual_repair_success(artifact_env):
    e = artifact_env
    revision = e["stage"]()
    e["service"].publish(e["id"], e["owner"], revision)
    old = e["files"].store.result_file(e["id"], e["owner"])
    e["files"].path(old["relative_path"], e["owner"]).write_bytes(b"broken")
    fail = e["service"]._fail

    def repair_before_failure(*args, **kwargs):
        with patch.object(e["service"], "_fail", fail):
            assert e["service"].publish(e["id"], e["owner"], revision, manual=True)["available"]
        fail(*args, **kwargs)

    with patch.object(e["service"], "_fail", side_effect=repair_before_failure):
        state = e["service"].publish(e["id"], e["owner"], revision)
    assert state["available"] and state["status"] == "published"


def test_retry_rechecks_success_before_marking_same_revision_pending(artifact_env):
    e = artifact_env
    e["stage"]()
    read = e["service"].state
    once = True

    def publish_after_stale_state(evaluation_id, owner):
        nonlocal once
        state = read(evaluation_id, owner)
        if once:
            once = False
            with patch.object(e["service"], "state", read):
                assert e["service"].publish(evaluation_id, owner, state["revision"])["available"]
        return state

    with patch.object(e["service"], "state", side_effect=publish_after_stale_state):
        with patch.object(
            e["service"],
            "_enqueue",
            side_effect=OSError("must not enqueue an already published version"),
        ) as enqueue:
            state = e["service"].retry(e["id"], e["owner"])
            assert state["available"]
            enqueue.assert_not_called()


@pytest.mark.parametrize("kind", ["json", "chart"])
def test_download_content_and_headers_are_one_immutable_revision(artifact_env, kind):
    e = artifact_env
    first = e["stage"]()
    e["service"].publish(e["id"], e["owner"], first)
    read = e["files"].read_file
    render = e["files"]._render_results
    raced = False
    rendered = []

    def advance_after_read(*args, **kwargs):
        nonlocal raced
        result = read(*args, **kwargs)
        if not raced:
            raced = True
            with patch.object(e["files"], "read_file", read):
                latest = e["stage"]("paused", 2)
                assert e["service"].publish(e["id"], e["owner"], latest)["available"]
        return result

    def capture_render(payload, *args, **kwargs):
        rendered.append((payload["revision"], payload["complete"]))
        return render(payload, *args, **kwargs)

    path = f"/api/v1/results/{e['id']}/" + ("download" if kind == "json" else "charts/success-rate")
    with (
        patch.object(e["files"], "read_file", side_effect=advance_after_read),
        patch.object(e["files"], "_render_results", side_effect=capture_render),
    ):
        response = e["client"].get(path, headers=auth_headers(e["alice"]))
    assert raced
    assert response.status_code in {200, 409}
    if response.status_code == 200:
        assert int(response.headers["x-artifact-revision"]) == rendered[-1][0]
        assert (response.headers["x-artifact-completeness"] == "complete") == rendered[-1][1]
        if kind == "json":
            assert response.json()["revision"] == rendered[-1][0]


def test_cancel_api_durably_stages_terminal_snapshot_without_worker_finally(worker_env):
    e, _, _ = worker_env
    from api.db.models import AsyncTask, EvaluationArtifactPublication

    first = e["stage"]("running", 2)
    with e["app"].state.task_session_factory() as db:
        evaluation = db.get(Evaluation, e["id"])
        db.get(AsyncTask, evaluation.async_task_id).status = "running"
        db.commit()
    e["service"].publish(e["id"], e["owner"], first)
    with (
        patch("src.task_manager.celery_app.AsyncResult") as result,
        patch("src.task_manager.celery_app.control.revoke") as revoke,
        patch("src.task_manager.celery_app.send_task") as send,
    ):
        result.return_value.state = "STARTED"
        response = e["client"].post(
            f"/api/v1/evaluations/{e['id']}/cancel", headers=auth_headers(e["alice"])
        )
        assert response.status_code == 200, response.text
        assert revoke.call_args.kwargs["terminate"] is True
        with e["app"].state.task_session_factory() as db:
            publication = db.get(EvaluationArtifactPublication, e["id"])
            assert publication.snapshot["state"] == "cancelled"
            assert publication.revision > first
            latest = publication.revision
        assert any(
            call.args[0] == "src.tasks.artifacts.publish_evaluation_artifacts"
            for call in send.call_args_list
        )
    # A terminated worker never runs finally; only the durable independent publication runs.
    assert e["service"].publish(e["id"], e["owner"], latest)["available"]
    response = e["client"].get(
        f"/api/v1/results/{e['id']}/download", headers=auth_headers(e["alice"])
    )
    assert (
        response.status_code == 200
        and response.json()["state"] == "cancelled"
        and not response.json()["complete"]
    )


def test_unavailable_broker_has_bounded_retry_and_no_result_backend_subscription():
    import socket

    from kombu import Connection
    from kombu.exceptions import OperationalError

    from api.services.artifact_service import EvaluationArtifactService
    from src.celery_app import celery_app

    with socket.socket() as unavailable:
        unavailable.bind(("127.0.0.1", 0))
        uri = f"redis://127.0.0.1:{unavailable.getsockname()[1]}/0"
        with patch.object(
            celery_app,
            "connection_for_write",
            side_effect=lambda **kwargs: Connection(uri, **kwargs),
        ) as connect:
            with patch.object(
                celery_app.backend,
                "on_task_call",
                side_effect=AssertionError("Must not open result backend for artifact publication"),
            ) as backend:
                with pytest.raises(OperationalError):
                    EvaluationArtifactService._send("evaluation", "owner", 1, False)
                backend.assert_not_called()
            options = next(
                call.kwargs for call in connect.call_args_list if "connect_timeout" in call.kwargs
            )
            assert options["connect_timeout"] == 2
            assert options["transport_options"]["max_retries"] == 0
            assert options["transport_options"]["socket_timeout"] == 2


def test_legacy_cancel_without_async_task_stages_same_terminal_snapshot(artifact_env):
    e = artifact_env
    first = e["stage"]("running", 2)
    e["service"].publish(e["id"], e["owner"], first)
    response = e["client"].post(
        f"/api/v1/evaluations/{e['id']}/cancel", headers=auth_headers(e["alice"])
    )
    assert response.status_code == 200, response.text
    from api.db.models import EvaluationArtifactPublication

    with e["app"].state.task_session_factory() as db:
        publication = db.get(EvaluationArtifactPublication, e["id"])
        assert publication.snapshot["state"] == "cancelled"
        latest = publication.revision
    assert e["service"].publish(e["id"], e["owner"], latest)["available"]
