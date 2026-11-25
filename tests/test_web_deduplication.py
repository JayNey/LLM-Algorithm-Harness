"""Reviewed merges must never mutate a library or silently select a primary."""

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_api_evaluation_options import (  # noqa: F401
    api,
    model_key,
    personal,
    populated,
    problem,
    recommendation_history,
)

BASE = "/api/v1/problems/governance/deduplication"


@pytest.fixture
def library(api):  # noqa: F811
    app, client, users = api
    rows = [
        {
            **problem("a", "Binary search sorted array"),
            "tags": ["array"],
            "source_platform": "leetcode",
            "source_problem_id": "1",
        },
        {
            **problem("b", "Alternative binary search"),
            "tags": ["search"],
            "description": "Keep this exact description",
            "source_platform": "leetcode",
            "source_problem_id": "1",
            "public_test_cases": [{"input": {"n": 1}, "expected_output": 2}],
        },
        {**problem("c", "Graph traversal"), "source_platform": "cf", "source_problem_id": "2"},
        {**problem("d", "Other graph"), "source_platform": "cf", "source_problem_id": "2"},
        problem("e", "Unique numeric integration"),
    ]
    personal(app, users["alice"][1], rows)
    personal(app, users["bob"][1], [problem("secret")])
    return app, client, users, rows


def scan(client, headers, threshold=1):
    result = client.post(BASE + "/preview", headers=headers, json={"threshold": threshold})
    assert result.status_code == 200, result.text
    return result.json()["data"]


def confirmation(preview, primary="b"):
    group = next(g for g in preview["groups"] if g["problems"][0]["problem_id"] == "a")
    return {
        "threshold": 1,
        "preview_token": preview["preview_token"],
        "name": "Reviewed",
        "groups": [{"group_id": group["group_id"], "primary_id": primary}],
    }


def test_preview_and_selected_primary_preserve_complete_payload_and_skipped_groups(library):
    app, client, users, rows = library
    headers, owner = users["alice"]
    store = app.state.files.store
    revision = store.dataset_snapshot(owner)[0]
    preview = scan(client, headers)
    assert len(preview["groups"]) == 2
    group = preview["groups"][0]
    (match,) = group["matches"]
    assert (match["left_id"], match["right_id"], match["fingerprint"]) == ("a", "b", True)
    assert 0 <= match["similarity"] < 1
    merged = group["merges"]["b"]
    assert merged["description"] == "Keep this exact description"
    assert merged["tags"] == ["search", "array"]
    assert merged["merged_from"] == ["a"]
    assert store.dataset_snapshot(owner) == (revision, rows)
    saved = client.post(BASE + "/versions", headers=headers, json=confirmation(preview))
    assert saved.status_code == 201, saved.text
    version = saved.json()["data"]
    assert version["problem_count"] == 4
    _, payload = store.dataset_version(owner, version["id"])
    assert payload == [merged, *rows[2:]]
    assert store.dataset_snapshot(owner) == (revision, rows)
    detail = client.get("/api/v1/problems/governance/versions/" + version["id"], headers=headers)
    assert detail.json()["data"]["problems"][0]["merged_from"] == ["a"]
    assert (
        client.get(
            "/api/v1/problems/governance/versions/" + version["id"], headers=users["bob"][0]
        ).status_code
        == 404
    )


def test_confirmation_is_persistent_and_concurrent_idempotent(library):
    from api.files.deduplication import DeduplicationSaveRequest, save_deduplication
    from api.files.store import FileStore

    app, client, users, _ = library
    headers, owner = users["alice"]
    request = DeduplicationSaveRequest.model_validate(confirmation(scan(client, headers)))
    store = app.state.files.store
    with ThreadPoolExecutor(max_workers=4) as pool:
        versions = list(pool.map(lambda _: save_deduplication(store, owner, request), range(4)))
    assert len({v.id for v in versions}) == 1
    assert len(store.dataset_versions(owner)) == 1
    store.append_problem(owner, problem("new"), max_bytes=100_000, max_items=20)
    reopened = FileStore(store.auth_store)
    assert save_deduplication(reopened, owner, request).id == versions[0].id


def test_stale_forged_empty_and_cross_owner_confirmations_do_not_save(library):
    app, client, users, _ = library
    headers, owner = users["alice"]
    preview = scan(client, headers)
    valid = confirmation(preview)
    for groups in (
        [],
        [*valid["groups"], *valid["groups"]],
        [{"group_id": "forged", "primary_id": "b"}],
        [{**valid["groups"][0], "primary_id": "secret"}],
    ):
        assert client.post(
            BASE + "/versions", headers=headers, json={**valid, "groups": groups}
        ).status_code in (400, 422)
    assert client.post(BASE + "/versions", headers=users["bob"][0], json=valid).status_code == 409
    app.state.files.store.append_problem(owner, problem("new"), max_bytes=100_000, max_items=20)
    assert client.post(BASE + "/versions", headers=headers, json=valid).status_code == 409
    assert app.state.files.store.dataset_versions(owner) == []
    client.cookies.clear()
    assert client.post(BASE + "/preview", json={"threshold": 0.9}).status_code == 401


@pytest.mark.parametrize("threshold", [-0.1, 1.1, "NaN", "Infinity"])
def test_invalid_threshold_is_rejected(library, threshold):
    _, client, users, _ = library
    assert (
        client.post(
            BASE + "/preview", headers=users["alice"][0], json={"threshold": threshold}
        ).status_code
        == 400
    )


def test_empty_vocabulary_still_finds_fingerprints(api):  # noqa: F811
    app, client, users = api
    rows = [
        {
            **problem(pid, "the"),
            "description": "a",
            "source_platform": "x",
            "source_problem_id": "1",
        }
        for pid in ("a", "b")
    ]
    personal(app, users["alice"][1], rows)
    assert len(scan(client, users["alice"][0], 0.9)["groups"]) == 1
    assert scan(client, users["bob"][0])["groups"] == []


def test_text_candidates_do_not_overlap_and_tampered_threshold_is_rejected(api):  # noqa: F811
    app, client, users = api
    headers, owner = users["alice"]
    rows = [problem(pid, "Identical binary search") for pid in ("a", "b", "c", "d")]
    personal(app, owner, rows)
    assert scan(client, headers, 1)["groups"] == []
    preview = scan(client, headers, 0.9)
    assert [[p["problem_id"] for p in g["problems"]] for g in preview["groups"]] == [
        ["a", "b"],
        ["c", "d"],
    ]
    assert preview["groups"][0]["matches"][0]["similarity"] > 0.9
    request = {
        "threshold": 0.8,
        "preview_token": preview["preview_token"],
        "name": "Forged",
        "groups": [{"group_id": preview["groups"][0]["group_id"], "primary_id": "a"}],
    }
    assert client.post(BASE + "/versions", headers=headers, json=request).status_code == 409


def test_source_changed_at_commit_is_rejected_and_pruned_receipt_does_not_recreate(
    library, monkeypatch
):
    from fastapi import HTTPException

    from api.files.deduplication import DeduplicationSaveRequest, save_deduplication

    app, client, users, _ = library
    headers, owner = users["alice"]
    store = app.state.files.store
    request = DeduplicationSaveRequest.model_validate(confirmation(scan(client, headers)))
    original = store.save_dataset_version

    def mutate_then_save(*args, **kwargs):
        store.append_problem(owner, problem("new"), max_bytes=100_000, max_items=20)
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "save_dataset_version", mutate_then_save)
    with pytest.raises(HTTPException) as conflict:
        save_deduplication(store, owner, request)
    assert conflict.value.status_code == 409
    assert store.dataset_versions(owner) == []
    monkeypatch.setattr(store, "save_dataset_version", original)
    request = DeduplicationSaveRequest.model_validate(confirmation(scan(client, headers)))
    saved = save_deduplication(store, owner, request)
    revision, rows = store.dataset_snapshot(owner)
    original(owner, revision, "Next version", rows, max_versions=1)
    with pytest.raises(HTTPException) as gone:
        save_deduplication(store, owner, request)
    assert gone.value.status_code == 410
    assert saved.id not in [v["id"] for v in store.dataset_versions(owner)]
    assert len(store.dataset_versions(owner)) == 1


def test_merged_version_creates_frozen_evaluation_and_preserves_existing_references(
    recommendation_history,  # noqa: F811
    monkeypatch,
):
    from api.db.models import Evaluation
    from src.tasks.evaluation import _freeze_problem, _resolve_execution_context

    app, client, users = recommendation_history
    headers, owner = users["alice"]
    store = app.state.files.store
    rows = [
        {
            **problem(pid, "Binary search"),
            "source_platform": "lc",
            "source_problem_id": "1",
            "tags": [pid],
        }
        for pid in ("p1", "p2")
    ]
    with store.connection() as db:
        db.execute(
            "UPDATE api_file_datasets SET payload=? WHERE user_id=?",
            (json.dumps(rows), owner),
        )
    revision, _ = store.dataset_snapshot(owner)
    old = store.save_dataset_version(owner, revision, "Before merge", rows)
    old_set = store.save_recommendation_set(owner, "Existing", ["p1", "p2"])
    before = client.get("/api/v1/results/mine", headers=headers).json()["data"]
    preview = scan(client, headers)
    result = client.post(
        BASE + "/versions",
        headers=headers,
        json={
            "threshold": 1,
            "preview_token": preview["preview_token"],
            "name": "Merged",
            "groups": [{"group_id": preview["groups"][0]["group_id"], "primary_id": "p2"}],
        },
    )
    assert result.status_code == 201, result.text
    version_id = result.json()["data"]["id"]
    created = client.post(
        "/api/v1/evaluations/with-dataset-version",
        headers=headers,
        json={
            "api_key_id": model_key(app, users),
            "model": "test",
            "problem_ids": ["p2"],
            "strategy_names": ["vanilla"],
            "dataset_version_id": version_id,
        },
    )
    assert created.status_code == 201, created.text
    with store.connection() as db:
        db.execute("UPDATE api_file_datasets SET payload='[]' WHERE user_id=?", (owner,))
    monkeypatch.setattr("api.auth.config.AuthSettings", lambda: app.state.auth.settings)
    with app.state.task_session_factory() as db:
        evaluation = db.get(Evaluation, created.json()["data"]["evaluation_id"])
        frozen = _freeze_problem(
            _resolve_execution_context(evaluation, app.state.task_session_factory), "p2"
        )
    assert frozen["problem"]["tags"] == ["p2", "p1"]
    assert frozen["problem"]["description"] == rows[1]["description"]
    assert store.dataset_version(owner, old["id"])[1] == rows
    assert store.recommendation_set(owner, old_set)[1] == ["p1", "p2"]
    assert client.get("/api/v1/results/mine", headers=headers).json()["data"] == before
