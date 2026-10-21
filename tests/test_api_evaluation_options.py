"""真实选项接口：归属隔离、有效题目集合及严格分页契约。"""

import json
import secrets

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.db.problem_store import ProblemStore
from api.files.config import FileSettings
from api.main import create_app
from api.monitoring.config import MonitorSettings
from src.harness import AlgorithmHarness

PASSWORD = "evaluation-options-password!"
BASE = "/api/v1/evaluation-options"


@pytest.fixture
def api(tmp_path):
    app = create_app(
        AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
            AUTH_RATE_LIMIT=1000,
            AUTH_PROTECTED_RATE_LIMIT=1000,
        ),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        database_url=f"sqlite:///{tmp_path / 'business.sqlite3'}",
        monitor_settings=MonitorSettings(_env_file=None, MONITOR_ADMIN_USER_IDS=[]),
    )
    with TestClient(app) as client:
        users = {}
        for name in ("alice", "bob"):
            registered = client.post(
                "/api/v1/auth/register",
                json={"username": name, "email": name + "@example.org", "password": PASSWORD},
            )
            assert registered.status_code == 201, registered.text
            login = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
            assert login.status_code == 200, login.text
            headers = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
            me = client.get("/api/v1/users/me", headers=headers)
            assert me.status_code == 200, me.text
            users[name] = (headers, me.json()["data"]["id"])
            client.cookies.clear()
        yield app, client, users


def problem(pid, title="Shared title", difficulty="easy"):
    return {
        "problem_id": pid,
        "title": title,
        "difficulty": difficulty,
        "description": "Secret description",
        "test_cases": [{"input": {}, "expected_output": "hidden-answer"}],
        "source_url": "/private/server/path",
    }


def personal(app, owner_id, rows):
    # Seed owner-scoped storage, including legacy duplicates, as read by the worker.
    with app.state.files.store.connection() as db:
        db.execute(
            "INSERT INTO api_file_datasets(user_id,payload,updated_at) VALUES (?,?,0)",
            (owner_id, json.dumps(rows)),
        )


@pytest.fixture
def populated(api):
    app, client, users = api
    ProblemStore(app.state.task_session_factory).upsert_import(
        [problem("p3"), problem("p1"), problem("p2", difficulty=None)]
    )
    personal(
        app, users["alice"][1], [problem("p1", "Old personal"), problem("p1", "My version", "hard")]
    )
    personal(app, users["bob"][1], [problem("bob-secret", "Other user secret")])
    return app, client, users


def test_regular_user_gets_real_strategies_and_effective_source_counts(populated):
    _, client, users = populated
    response = client.get(BASE, headers=users["alice"][0])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    data = response.json()["data"]
    assert {item["name"] for item in data["strategies"]} == set(AlgorithmHarness.STRATEGY_MAP)
    assert {item["id"]: item["problem_count"] for item in data["sources"]} == {
        "shared": 2,
        "personal": 1,
    }
    assert all(item["label"] for item in data["sources"])
    assert client.get("/api/v1/config/strategies", headers=users["alice"][0]).status_code == 403


def test_problem_page_uses_personal_override_and_contains_metadata_only(populated):
    _, client, users = populated
    response = client.get(BASE + "/problems?limit=2", headers=users["alice"][0])
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {
        "items": [
            {"problem_id": "p1", "title": "My version", "difficulty": "hard", "source": "personal"},
            {"problem_id": "p2", "title": "Shared title", "difficulty": None, "source": "shared"},
        ],
        "total": 3,
        "limit": 2,
        "offset": 0,
        "has_more": True,
    }


@pytest.mark.parametrize(
    "query,ids,total,has_more",
    [
        ("limit=2&offset=2", ["p3"], 3, False),
        ("offset=50", [], 3, False),
        ("source=shared&limit=1", ["p2"], 2, True),
        ("source=personal", ["p1"], 1, False),
    ],
)
def test_filters_before_pagination_and_counts_effective_collection(
    populated, query, ids, total, has_more
):
    _, client, users = populated
    response = client.get(BASE + "/problems?" + query, headers=users["alice"][0])
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert [item["problem_id"] for item in page["items"]] == ids
    assert page["total"] == total
    assert page["has_more"] is has_more


def test_another_user_sees_shared_original_and_only_own_import(populated):
    _, client, users = populated
    response = client.get(BASE + "/problems", headers=users["bob"][0])
    assert response.status_code == 200, response.text
    page = response.json()["data"]
    assert page["total"] == 4
    assert page["items"][0]["problem_id"] == "bob-secret"
    assert page["items"][1] == {
        "problem_id": "p1",
        "title": "Shared title",
        "difficulty": "easy",
        "source": "shared",
    }
    sources = client.get(BASE, headers=users["bob"][0]).json()["data"]["sources"]
    assert {item["id"]: item["problem_count"] for item in sources} == {"shared": 3, "personal": 1}


def test_empty_collections_return_success_without_examples(api):
    _, client, users = api
    response = client.get(BASE, headers=users["alice"][0])
    assert response.status_code == 200, response.text
    assert response.json()["data"]["sources"] == []
    response = client.get(BASE + "/problems", headers=users["alice"][0])
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
        "has_more": False,
    }


@pytest.mark.parametrize("path", [BASE, BASE + "/problems"])
def test_unauthenticated_options_require_identity(api, path):
    _, client, _ = api
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "query", ["source=other", "limit=0", "limit=101", "limit=1.5", "offset=-1", "offset=x"]
)
def test_invalid_pagination_and_source_are_rejected(api, query):
    _, client, users = api
    response = client.get(BASE + "/problems?" + query, headers=users["alice"][0])
    assert response.status_code == 400, response.text
