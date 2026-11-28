"""Version downloads preserve frozen data and the changes approved at save time."""

import json

import pytest
from fastapi import HTTPException
from test_api_evaluation_options import (  # noqa: F401
    api,
    model_key,
    personal,
    populated,
    recommendation_history,
)

from api.files.store import FileStore
from src.models import Problem

BASE = "/api/v1/problems/governance/versions"


@pytest.fixture
def governed(recommendation_history):  # noqa: F811
    app, client, users = recommendation_history
    headers, owner = users["alice"]
    row = Problem(
        problem_id="p1",
        title="Binary Search",
        description="Return the index of x in the sorted input array.",
        difficulty="easy",
        tags=["  ARRAY  "],
        constraints="1 <= n <= 100",
        source_platform="custom",
        source_problem_id="original-1",
        source_url="https://example.org/problems/1",
        source_version="release-2",
        source_metadata={"license": "CC0", "nested": {"original": True}},
        entry_point="solution(nums, x)",
        judge_config={"comparison": "exact", "float_tolerance": 0.01},
        public_test_cases=[{"input": {"nums": [1, 2], "x": 2}, "expected_output": 1}],
        feedback_test_cases=[{"input": {"nums": [4], "x": 4}, "expected_output": 0}],
        hidden_test_cases=[
            {"input": {"nums": [7], "x": 6}, "expected_output": -1, "source": "hidden"}
        ],
    ).model_dump(mode="json")
    rows = [
        row,
        {**row, "problem_id": "p2", "tags": ["array"], "difficulty": "medium"},
        {**row, "problem_id": "unselected"},
    ]
    store = app.state.files.store
    with store.connection() as db:
        db.execute(
            "UPDATE api_file_datasets SET payload=? WHERE user_id=?", (json.dumps(rows), owner)
        )
    params = {"problem_ids": ["p1", "p2"], "run_ids": ["mine"]}
    preview = client.post("/api/v1/problems/governance/preview", headers=headers, json=params)
    assert preview.status_code == 200, preview.text
    changes = [
        {
            "problem_id": "p1",
            "normalize_tags": True,
            "suggested_tags": ["binary-search"],
            "apply_difficulty": True,
        },
        {"problem_id": "p2", "normalize_tags": True},  # Approved, but no actual difference.
    ]
    saved = client.post(
        BASE,
        headers=headers,
        json={
            "preview": params,
            "preview_token": preview.json()["data"]["preview_token"],
            "name": "Reviewed 数据",
            "changes": changes,
        },
    )
    assert saved.status_code == 201, saved.text
    return app, client, users, saved.json()["data"], rows


def test_report_records_actual_approvals_and_survives_source_changes(governed):
    app, client, users, version, rows = governed
    headers, owner = users["alice"]
    path = f"{BASE}/{version['id']}/report"
    downloaded = client.get(path, headers=headers)
    assert downloaded.status_code == 200, downloaded.text
    report = downloaded.json()
    assert report["version"] == version
    assert report["schema_version"] == 1
    assert report["preview"]["problem_ids"] == ["p1", "p2"]
    assert report["changes"] == [
        {
            "problem_id": "p1",
            "original_tags": ["  ARRAY  "],
            "new_tags": ["array", "binary-search"],
            "original_difficulty": "easy",
            "new_difficulty": "hard",
            "approval": {
                "normalize_tags": True,
                "suggested_tags": ["binary-search"],
                "apply_difficulty": True,
            },
        }
    ]
    assert app.state.files.store.dataset(owner) == rows
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_datasets SET payload='[]' WHERE user_id=?", (owner,))
    from api.db.models import EvaluationResult

    with app.state.task_session_factory() as db, db.begin():
        db.query(EvaluationResult).filter(EvaluationResult.evaluation_id == "mine").delete()
    # A fresh FileStore reads the persisted report, independent of live data/history.
    reopened = FileStore(app.state.files.store.auth_store)
    assert reopened.dataset_version_report(owner, version["id"]) == report
    assert client.get(path, headers=headers).content == downloaded.content


def test_complete_snapshot_download_reimports_and_evaluates(governed, monkeypatch):
    app, client, users, version, rows = governed
    headers, owner = users["alice"]
    path = f"{BASE}/{version['id']}"
    detail = client.get(path, headers=headers).json()["data"]
    assert "hidden_test_cases" not in detail["problems"][0]
    response = client.get(path + "/export", headers=headers)
    assert response.status_code == 200, response.text
    frozen = app.state.files.store.dataset_version(owner, version["id"])[1]
    assert response.json() == frozen
    assert frozen == [
        {**rows[0], "tags": ["array", "binary-search"], "difficulty": "hard"},
        rows[1],
    ]
    for item in frozen:
        assert Problem.model_validate(item).model_dump(mode="json") == item
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-type"].startswith("application/json")
    assert "attachment;" in response.headers["content-disposition"]
    assert version["id"] in response.headers["content-disposition"]
    assert client.get("/api/v1/problems/export", headers=headers).json() == rows

    imported = client.post(
        "/api/v1/problems/upload",
        headers=users["bob"][0],
        files={"file": ("version.json", response.content, "application/json")},
        data={"mode": "overwrite"},
    )
    assert imported.status_code == 200, imported.text
    assert app.state.files.store.dataset(users["bob"][1]) == frozen

    from api.db.models import Evaluation
    from src.tasks.evaluation import _freeze_problem, _resolve_execution_context

    for user, route, extra in (
        ("alice", "with-dataset-version", {"dataset_version_id": version["id"]}),
        ("bob", "with-selection", {}),
    ):
        created = client.post(
            f"/api/v1/evaluations/{route}",
            headers=users[user][0],
            json={
                "api_key_id": model_key(app, {"alice": users[user]}),
                "model": "test",
                "problem_ids": ["p1", "p2"],
                "strategy_names": ["vanilla"],
                **extra,
            },
        )
        assert created.status_code == 201, created.text
        monkeypatch.setattr("api.auth.config.AuthSettings", lambda: app.state.auth.settings)
        with app.state.task_session_factory() as db:
            evaluation = db.get(Evaluation, created.json()["data"]["evaluation_id"])
            context = _resolve_execution_context(evaluation, app.state.task_session_factory)
            assert _freeze_problem(context, "p1")["problem"] == frozen[0]
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_datasets SET payload='[]' WHERE user_id=?", (owner,))
    assert client.get(path + "/export", headers=headers).content == response.content


def test_downloads_reject_foreign_missing_and_pruned_versions(governed):
    app, client, users, version, _ = governed
    store = app.state.files.store
    headers, owner = users["alice"]
    for suffix in ("export", "report"):
        path = f"{BASE}/{version['id']}/{suffix}"
        assert client.get(path, headers=users["bob"][0]).status_code == 404
        assert client.get(f"{BASE}/missing/{suffix}", headers=headers).status_code == 404
        assert client.get(path).status_code == 401
    revision, rows = store.dataset_snapshot(owner)
    store.save_dataset_version(owner, revision, "Replacement", rows, max_versions=1)
    for suffix in ("export", "report"):
        assert client.get(f"{BASE}/{version['id']}/{suffix}", headers=headers).status_code == 404
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM api_dataset_version_reports").fetchone()[0] == 0


def test_legacy_version_remains_exportable_after_incremental_schema_upgrade(governed):
    app, client, users, _, _ = governed
    store = app.state.files.store
    headers, owner = users["alice"]
    revision, rows = store.dataset_snapshot(owner)
    old = store.save_dataset_version(owner, revision, "Legacy", rows)
    with store.connection() as db:
        db.execute("DROP TABLE api_dataset_version_reports")
    reopened = FileStore(store.auth_store)
    assert reopened.dataset_version(owner, old["id"])[1] == rows
    assert client.get(f"{BASE}/{old['id']}/export", headers=headers).json() == rows
    report = client.get(f"{BASE}/{old['id']}/report", headers=headers)
    assert report.status_code == 409
    assert "Historical change report is unavailable" in report.text


def test_failed_report_write_rolls_back_version_and_stale_source_is_rejected(governed):
    app, _, users, _, _ = governed
    store = app.state.files.store
    owner = users["alice"][1]
    revision, rows = store.dataset_snapshot(owner)
    before = store.dataset_versions(owner)
    with pytest.raises(TypeError):
        store.save_dataset_version(owner, revision, "Broken", rows, change_report={"bad": object()})
    assert store.dataset_versions(owner) == before
    with store.connection() as db:
        db.execute("UPDATE api_file_datasets SET revision=revision+1 WHERE user_id=?", (owner,))
    with pytest.raises(HTTPException) as error:
        store.save_dataset_version(owner, revision, "Stale", rows, change_report={"changes": []})
    assert error.value.status_code == 409
    assert store.dataset_versions(owner) == before


def test_partial_approval_keeps_unapproved_tags_and_problems(governed):
    app, client, users, _, rows = governed
    headers, owner = users["alice"]
    params = {"problem_ids": ["p1", "p2"], "run_ids": ["mine"]}
    preview = client.post("/api/v1/problems/governance/preview", headers=headers, json=params)
    saved = client.post(
        BASE,
        headers=headers,
        json={
            "preview": params,
            "preview_token": preview.json()["data"]["preview_token"],
            "name": "Difficulty only",
            "changes": [{"problem_id": "p1", "apply_difficulty": True}],
        },
    )
    assert saved.status_code == 201, saved.text
    version_id = saved.json()["data"]["id"]
    assert app.state.files.store.dataset_version(owner, version_id)[1] == [
        {**rows[0], "difficulty": "hard"},
        rows[1],
    ]
    changes = client.get(f"{BASE}/{version_id}/report", headers=headers).json()["changes"]
    assert len(changes) == 1
    assert changes[0]["original_tags"] == changes[0]["new_tags"] == rows[0]["tags"]
    assert changes[0]["approval"] == {
        "normalize_tags": False,
        "suggested_tags": [],
        "apply_difficulty": True,
    }


def test_deduplicated_version_exports_its_full_merged_snapshot(governed):
    app, client, users, _, _ = governed
    headers, owner = users["alice"]
    base = "/api/v1/problems/governance/deduplication"
    preview = client.post(base + "/preview", headers=headers, json={"threshold": 1})
    assert preview.status_code == 200, preview.text
    data = preview.json()["data"]
    group = data["groups"][0]
    primary = group["problems"][0]["problem_id"]
    saved = client.post(
        base + "/versions",
        headers=headers,
        json={
            "threshold": 1,
            "preview_token": data["preview_token"],
            "name": "Merged",
            "groups": [{"group_id": group["group_id"], "primary_id": primary}],
        },
    )
    assert saved.status_code == 201, saved.text
    version_id = saved.json()["data"]["id"]
    exported = client.get(f"{BASE}/{version_id}/export", headers=headers)
    assert exported.status_code == 200
    assert exported.json() == app.state.files.store.dataset_version(owner, version_id)[1]
    merged = next(row for row in exported.json() if row["problem_id"] == primary)
    assert merged["merged_from"]
    assert merged["hidden_test_cases"] and merged["judge_config"] and merged["source_metadata"]
    assert client.get(f"{BASE}/{version_id}/report", headers=headers).status_code == 409
