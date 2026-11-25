"""HTTP contract and migration checks for owner-scoped incremental Web runs."""

import secrets
import uuid

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from api.auth.config import AuthSettings
from api.db.migrate import downgrade, offline_upgrade_sql, upgrade
from api.db.models import Evaluation, EvaluationResult, Problem, utcnow
from api.files.config import FileSettings
from api.main import create_app
from api.services.evaluation_reuse import build_plan
from src.models import ExecutionResult


@pytest.fixture
def reuse_app(tmp_path):
    settings = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )
    app = create_app(
        settings,
        FileSettings(UPLOAD_DIR=tmp_path / "files"),
        database_url=f"sqlite:///{tmp_path / 'business.sqlite3'}",
    )
    with TestClient(app) as client:

        def login(name):
            password = "a-long-test-password-!"
            client.post(
                "/api/v1/auth/register",
                json={"username": name, "email": name + "@example.org", "password": password},
            )
            token = client.post(
                "/api/v1/auth/login", json={"username": name, "password": password}
            ).json()["data"]["access_token"]
            headers = {"Authorization": "Bearer " + token}
            key = client.post(
                "/api/v1/api-keys",
                headers=headers,
                json={
                    "provider": "openai",
                    "key_name": "offline test",
                    "api_key": "sk-offline-test-secret",
                },
            ).json()["data"]["id"]
            return headers, key

        first = login("alice")
        second = login("bob")
        with Session(app.state.evaluations.engine) as db, db.begin():
            db.add(
                Problem(
                    id=str(uuid.uuid4()),
                    problem_id="p1",
                    title="Add",
                    description="Add numbers",
                    difficulty="easy",
                    tags=["math"],
                    test_cases=[{"input": [1, 2], "expected_output": 3}],
                )
            )
        yield app, client, first, second


def _payload(key, **extra):
    return {
        "api_key_id": key,
        "model": "gpt-4o-mini",
        "problem_ids": ["p1"],
        "strategy_names": ["vanilla"],
        "reuse_history": True,
        **extra,
    }


def _seed_compatible(app, client, headers, key):
    response = client.post(
        "/api/v1/evaluations", headers=headers, json=_payload(key, reuse_history=False)
    )
    assert response.status_code == 201, response.text
    eid = response.json()["data"]["evaluation_id"]
    factory = app.state.evaluations._session_factory
    with factory() as db:
        ev = db.get(Evaluation, eid)
        plan = build_plan(ev, factory, auth=app.state.auth)
        selection = plan["units"][0]
        ev.status = "completed"
        ev.completed_at = utcnow()
        ev.completed_count = 1
        ev.run_id = ev.web_run_id
        ev.spent_usd = 0.3
        result = ExecutionResult(
            problem_id="p1",
            strategy="vanilla",
            generated_code="print(3)",
            status="success",
            total_tokens=10,
            metadata={"cost_usd": 0.3},
        )
        db.add(
            EvaluationResult(
                id=str(uuid.uuid4()),
                evaluation_id=eid,
                problem_id="p1",
                strategy_name="vanilla",
                status="success",
                execution_payload=result.model_dump(mode="json"),
                metrics={
                    "actually_executed": True,
                    "execution_fingerprint": selection["execution_fingerprint"],
                    "problem_fingerprint": selection["problem_fingerprint"],
                    "total_tokens": 10,
                    "cost_usd": 0.3,
                    "cost_known": True,
                    "iterations": 0,
                },
            )
        )
        db.commit()
    return eid


def test_preview_creation_owner_scope_and_frozen_plan(reuse_app):
    app, client, (alice, key), (bob, other_key) = reuse_app
    source = _seed_compatible(app, client, alice, key)
    factory = app.state.evaluations._session_factory
    with factory() as db:
        before = db.query(Evaluation).count()
    reply = client.post("/api/v1/evaluations/reuse-preview", headers=alice, json=_payload(key))
    assert reply.status_code == 200, reply.text
    preview = reply.json()["data"]
    assert preview["reused_units"] == 1 and preview["new_units"] == 0
    assert preview["units"][0]["source"]["evaluation_id"] == source
    assert "test_cases" not in reply.text and "sk-offline-test-secret" not in reply.text
    with factory() as db:
        assert db.query(Evaluation).count() == before
    other = client.post("/api/v1/evaluations/reuse-preview", headers=bob, json=_payload(other_key))
    assert other.json()["data"]["reused_units"] == 0
    assert source not in other.text
    created = client.post(
        "/api/v1/evaluations/with-selection", headers=alice, json=_payload(key)
    ).json()["data"]
    assert created["reuse_history"] and created["reused_units"] == 1 and created["new_units"] == 0
    with factory() as db:
        stored = db.get(Evaluation, created["evaluation_id"])
        assert stored.reuse_plan["problems"]["p1"]["problem"]["description"] == "Add numbers"
        assert "api_key" not in stored.reuse_plan["llm"]
        assert "reuse_plan" not in created
        db.query(Problem).filter_by(problem_id="p1").one().description = "Changed after creation"
        db.query(EvaluationResult).filter_by(evaluation_id=source).delete()
        db.delete(db.get(Evaluation, source))
        db.commit()
        assert (
            db.get(Evaluation, created["evaluation_id"]).reuse_plan["units"][0]["result"][
                "metrics"
            ]["total_tokens"]
            == 10
        )
    client.cookies.clear()
    assert client.post("/api/v1/evaluations/reuse-preview", json=_payload(key)).status_code == 401
    assert client.post(
        "/api/v1/evaluations/reuse-preview", headers=bob, json=_payload(key)
    ).status_code in {403, 404}


def test_version_preview_preserves_version_and_missing_input_fails(reuse_app, monkeypatch):
    app, client, (headers, key), _ = reuse_app
    personal = {
        "problem_id": "p1",
        "title": "Personal add",
        "description": "Versioned statement",
        "difficulty": "easy",
        "tags": [],
        "public_test_cases": [{"input": [1], "expected_output": 1}],
    }
    seen = []

    def version(store, owner, version_id):
        seen.append(version_id)
        return {}, [personal]

    monkeypatch.setattr("api.files.store.FileStore.dataset_version", version)
    request = _payload(key, dataset_version_id="version-fixed")
    preview = client.post("/api/v1/evaluations/reuse-preview", headers=headers, json=request)
    assert preview.status_code == 200, preview.text
    created = client.post("/api/v1/evaluations/with-dataset-version", headers=headers, json=request)
    assert created.status_code == 201, created.text
    with app.state.evaluations._session() as db:
        ev = db.get(Evaluation, created.json()["data"]["evaluation_id"])
        snapshot = ev.reuse_plan["problems"]["p1"]
        assert snapshot["dataset_version_id"] == "version-fixed"
        assert snapshot["problem"]["description"] == personal["description"]
    assert seen and set(seen) == {"version-fixed"}
    missing = client.post(
        "/api/v1/evaluations", headers=headers, json=_payload(key, problem_ids=["missing"])
    )
    assert missing.status_code == 400, missing.text


def test_reuse_migration_roundtrip_and_postgres_sql(tmp_path):
    url = f"sqlite:///{tmp_path / 'migration.sqlite3'}"
    upgrade(url, "0010")
    engine = create_engine(url)
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO evaluations (id,user_id,status,strategy_names,problem_ids,problem_count,spent_usd,completed_count,failed_count,created_at,updated_at) VALUES ('old','owner','pending','[]','[]',0,0,0,0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
            )
        )
    upgrade(url)
    with engine.connect() as db:
        assert db.execute(
            text("SELECT reuse_history,reused_units,reuse_plan FROM evaluations WHERE id='old'")
        ).one() == (0, 0, None)
    downgrade(url, "0010")
    assert "reuse_plan" not in {
        column["name"] for column in inspect(engine).get_columns("evaluations")
    }
    upgrade(url)
    sql = offline_upgrade_sql("postgresql://localhost/offline")
    assert "ADD COLUMN reuse_history BOOLEAN DEFAULT false NOT NULL" in sql
    assert "ADD COLUMN reuse_plan JSON" in sql
    engine.dispose()


def test_result_pagination_preserves_provenance_and_new_cost(reuse_app):
    from src.task_service import TaskUnit
    from src.tasks.evaluation import _record_unit_result

    app, client, (headers, key), (other, _) = reuse_app
    source = _seed_compatible(app, client, headers, key)
    created = client.post(
        "/api/v1/evaluations",
        headers=headers,
        json=_payload(key, strategy_names=["vanilla", "chain_of_thought"]),
    ).json()["data"]
    eid = created["evaluation_id"]
    with app.state.evaluations._session() as db:
        ev = db.get(Evaluation, eid)
        for selection in ev.reuse_plan["units"]:
            payload = (
                selection["result"]["execution_payload"]
                if selection.get("source")
                else ExecutionResult(
                    problem_id="p1",
                    strategy="chain_of_thought",
                    status="success",
                    generated_code="print(3)",
                    total_tokens=20,
                    metadata={"cost_usd": 0.05, "cost_known": True},
                ).model_dump(mode="json")
            )
            unit = TaskUnit(
                unit_id=str(uuid.uuid4()),
                problem_id="p1",
                strategy=selection["strategy"],
                status="completed",
                result=payload,
                problem_snapshot=ev.reuse_plan["problems"]["p1"],
            )
            _record_unit_result(db, ev, unit)
        ev.status = "completed"
        ev.run_id = ev.web_run_id
        ev.completed_count = 2
        ev.spent_usd = 0.05
        db.commit()
    for offset in [0, 1]:
        response = client.get(f"/api/v1/results/{eid}?limit=1&offset={offset}", headers=headers)
        assert response.status_code == 200, response.text
        detail = response.json()["data"]
        assert detail["reuse"] == {
            "total_units": 2,
            "reused_units": 1,
            "new_units": 1,
            "new_cost_usd": 0.05,
            "new_cost_unknown_count": 0,
        }
        assert detail["problems"]["total"] == 2
        row = detail["problems"]["items"][0]
        if row["reused"]:
            assert row["reuse_source"]["evaluation_id"] == source
            assert (
                row["tokens"] == 10 and row["original_cost_usd"] == 0.3 and row["new_cost_usd"] == 0
            )
    csv = client.get(f"/api/v1/reports/csv/{eid}", headers=headers)
    assert csv.status_code == 200 and "source_run_id" in csv.text and "new_cost_usd" in csv.text
    md = client.get(f"/api/v1/reports/markdown/{eid}", headers=headers)
    assert md.status_code == 200, md.text
    assert "New cost for this run: $0.050000" in md.text
    assert client.get(f"/api/v1/results/{eid}", headers=other).status_code == 404


def test_new_unknown_unit_cost_is_not_presented_as_free():
    from api.services.evaluation_results_service import _problem_item

    row = EvaluationResult(
        problem_id="p1",
        strategy_name="vanilla",
        status="success",
        metrics={
            "cost_usd": 0.0,
            "cost_unknown": True,
            "new_cost_usd": 0.0,
            "new_cost_unknown": True,
        },
    )
    item = _problem_item(row)
    assert item["new_cost_usd"] is None
    assert item["original_cost_usd"] is None
