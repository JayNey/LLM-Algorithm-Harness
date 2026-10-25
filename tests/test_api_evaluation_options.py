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


MODEL_SECRET = "sk-private-model-credential"


def model_key(app, users, provider="openai"):
    from api.auth.models import KeyCreate

    return app.state.auth.add_key(
        users["alice"][1],
        KeyCreate(provider=provider, key_name="Models", api_key=MODEL_SECRET),
    )["id"]


class ModelPage:
    def __init__(self, ids, following=None, error=None, elapsed=None):
        from types import SimpleNamespace

        self.data = [SimpleNamespace(id=value) for value in ids]
        self.following = following
        self.error = error
        self.has_more = following is not None or error is not None
        self.elapsed = elapsed
        self._options = SimpleNamespace(timeout=5.0)
        self.read_timeouts = []

    def has_next_page(self):
        return self.following is not None or self.error is not None

    def get_next_page(self):
        self.read_timeouts.append(self._options.timeout)
        if self.error:
            raise self.error
        if self.elapsed:
            self.elapsed()
        return self.following


def fake_models(monkeypatch, page, on_list=None):
    from types import SimpleNamespace

    class SDK:
        closed = False

        def __init__(self):
            self.options = []
            self.timeouts = []
            self.models = SimpleNamespace(list=self.list)

        def with_options(self, **kwargs):
            self.options.append(kwargs)
            return self

        def list(self, *, timeout):
            self.timeouts.append(timeout)
            if on_list:
                on_list()
            if isinstance(page, Exception):
                raise page
            return page

        def close(self):
            self.closed = True

    sdk = SDK()
    configs = []

    def construct(config):
        configs.append(config)
        return SimpleNamespace(client=sdk)

    # Patch only the external client boundary; auth, storage and route stay real.
    monkeypatch.setattr(
        "api.services.evaluation_options_service.LLMClient", construct, raising=False
    )
    return sdk, configs


@pytest.mark.parametrize("provider", ["openai", "anthropic", "siliconflow"])
def test_models_reads_owned_provider_pages_safely(api, monkeypatch, provider):
    from api.auth.service import PROVIDER_URLS

    app, client, users = api
    key_id = model_key(app, users, provider)
    page = ModelPage(["model-a"], ModelPage(["model-b"]))
    sdk, configs = fake_models(monkeypatch, page)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "source": "provider_api",
        "scope": "user_api_key",
        "provider": provider,
        "models": ["model-a", "model-b"],
        "complete": True,
    }
    assert response.headers["cache-control"] == "no-store"
    assert sdk.options == [{"timeout": 5.0, "max_retries": 0, "base_url": PROVIDER_URLS[provider]}]
    assert 0 < sdk.timeouts[0] <= 5
    assert sdk.closed is True
    assert configs[0].api_key.get_secret_value() == MODEL_SECRET
    assert configs[0].cache.enabled is False
    key = app.state.auth.owned_key(key_id, users["alice"][1])
    assert key["verified"] == key["verification_count"] == key["usage_count"] == 0


@pytest.mark.parametrize("state", ["other", "deleted", "missing"])
def test_models_rejects_unowned_or_missing_credentials_before_sdk(api, monkeypatch, state):
    app, client, users = api
    key_id = model_key(app, users)
    sdk, configs = fake_models(monkeypatch, ModelPage(["private"]))
    if state == "deleted":
        app.state.auth.delete_key(key_id, users["alice"][1])
    if state == "missing":
        key_id = "missing"
    who = "bob" if state == "other" else "alice"
    response = client.get(BASE + "/models", params={"api_key_id": key_id}, headers=users[who][0])
    assert response.status_code == 404
    assert configs == []


@pytest.mark.parametrize("state", ["replaced", "deleted"])
def test_models_rechecks_credential_after_enumeration(api, monkeypatch, state):
    from api.auth.models import KeyUpdate

    app, client, users = api
    key_id = model_key(app, users)

    def change():
        if state == "deleted":
            app.state.auth.delete_key(key_id, users["alice"][1])
        else:
            app.state.auth.update_key(
                key_id, users["alice"][1], KeyUpdate(api_key="replacement-secret")
            )

    sdk, _ = fake_models(monkeypatch, ModelPage(["private"]), change)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 409, response.text
    assert "private" not in response.text
    assert sdk.closed is True


@pytest.mark.parametrize("later", [False, True])
def test_models_provider_failure_is_sanitized_and_closed(api, monkeypatch, caplog, later):
    app, client, users = api
    key_id = model_key(app, users)
    failure = RuntimeError(MODEL_SECRET)
    sdk, _ = fake_models(monkeypatch, ModelPage(["a"], error=failure) if later else failure)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 503, response.text
    assert MODEL_SECRET not in response.text + caplog.text
    assert sdk.closed is True


@pytest.mark.parametrize(
    "count,more,complete",
    [(499, False, True), (500, False, False), (500, True, False), (501, False, False)],
)
def test_models_caps_actual_ids_without_reading_extra_page(api, monkeypatch, count, more, complete):
    app, client, users = api
    key_id = model_key(app, users)
    page = ModelPage([f"m{i}" for i in range(count)], ModelPage(["extra"]) if more else None)
    sdk, _ = fake_models(monkeypatch, page)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert len(data["models"]) == min(count, 500)
    assert data["models"][0] == "m0"
    assert data["complete"] is complete
    assert page.read_timeouts == []
    assert sdk.closed is True


def test_models_unknown_pagination_is_incomplete(api, monkeypatch):
    from types import SimpleNamespace

    app, client, users = api
    key_id = model_key(app, users)
    fake_models(monkeypatch, SimpleNamespace(data=[SimpleNamespace(id="actual-model")]))
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "source": "provider_api",
        "scope": "user_api_key",
        "provider": "openai",
        "models": ["actual-model"],
        "complete": False,
    }


@pytest.mark.parametrize(
    "metadata,complete",
    [({}, False), ({"has_more": True}, False), ({"has_more": False}, True)],
)
def test_models_anthropic_sdk_requires_explicit_end_metadata(api, monkeypatch, metadata, complete):
    from anthropic._models import FinalRequestOptions
    from anthropic.pagination import SyncPage
    from anthropic.types import ModelInfo

    app, client, users = api
    key_id = model_key(app, users, "anthropic")
    page = SyncPage[ModelInfo].model_construct(
        data=[
            ModelInfo(
                id="actual-model",
                created_at="2026-01-01T00:00:00Z",
                display_name="Actual model",
                type="model",
                lifecycle="active",
            )
        ],
        **metadata,
    )
    page._options = FinalRequestOptions.construct(method="get", url="/v1/models", params={})
    sdk, _ = fake_models(monkeypatch, page)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "source": "provider_api",
        "scope": "user_api_key",
        "provider": "anthropic",
        "models": ["actual-model"],
        "complete": complete,
    }
    assert sdk.closed is True


@pytest.mark.parametrize("provider", ["openai", "siliconflow"])
def test_models_openai_sdk_nonpaginated_contract_is_complete(api, monkeypatch, provider):
    from openai.pagination import SyncPage
    from openai.types import Model

    app, client, users = api
    key_id = model_key(app, users, provider)
    page = SyncPage[Model](
        object="list",
        data=[Model(id="actual-model", created=0, object="model", owned_by=provider)],
    )
    sdk, _ = fake_models(monkeypatch, page)
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"] == {
        "source": "provider_api",
        "scope": "user_api_key",
        "provider": provider,
        "models": ["actual-model"],
        "complete": True,
    }
    assert sdk.closed is True


@pytest.mark.parametrize(
    "elapsed,expected,complete", [(8.0, ["a", "b"], True), (10.0, ["a"], False)]
)
def test_models_budget_stops_dispatch_and_tightens_next_timeout(
    api, monkeypatch, elapsed, expected, complete
):
    from types import SimpleNamespace

    app, client, users = api
    key_id = model_key(app, users)
    now = [0.0]
    monkeypatch.setattr(
        "api.services.evaluation_options_service.time",
        SimpleNamespace(monotonic=lambda: now[0]),
        raising=False,
    )
    page = ModelPage(["a"], ModelPage(["b"]))
    sdk, _ = fake_models(monkeypatch, page, lambda: now.__setitem__(0, elapsed))
    response = client.get(
        BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0]
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["models"] == expected
    assert response.json()["data"]["complete"] is complete
    assert page.read_timeouts == ([2.0] if elapsed == 8 else [])
    assert sdk.closed is True


def test_models_uses_separate_user_rate_bucket(api, monkeypatch):
    app, client, users = api
    key_id = model_key(app, users)
    fake_models(monkeypatch, ModelPage(["a"]))
    app.state.auth.settings.AUTH_RATE_LIMIT = 1
    app.state.auth.limit("verify:" + users["alice"][1])
    first = client.get(BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0])
    second = client.get(BASE + "/models", params={"api_key_id": key_id}, headers=users["alice"][0])
    assert first.status_code == 200, first.text
    assert second.status_code == 429, second.text


def test_models_requires_identity(api):
    _, client, _ = api
    assert client.get(BASE + "/models?api_key_id=missing").status_code == 401


MONITOR_MODELS = "/api/v1/config/providers"


def make_model_admin(app, users):
    from uuid import UUID

    app.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(users["alice"][1])]


def test_monitor_models_default_is_explicitly_static(api, monkeypatch):
    app, client, users = api
    make_model_admin(app, users)
    sdk, configs = fake_models(monkeypatch, AssertionError("offline query called SDK"))
    response = client.get(MONITOR_MODELS, headers=users["alice"][0])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"] == "static_examples"
    assert data["scope"] == "offline_example_catalog"
    assert data["live_provider_availability_checked"] is False
    assert {row["provider"] for row in data["providers"]} == {
        "openai",
        "anthropic",
        "siliconflow",
        "local",
    }
    assert configs == []
    assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("provider", ["openai", "anthropic", "siliconflow"])
@pytest.mark.parametrize("count,complete", [(2, True), (500, False), (0, True)])
def test_monitor_models_matches_owned_dynamic_listing(api, monkeypatch, provider, count, complete):
    app, client, users = api
    make_model_admin(app, users)
    key_id = model_key(app, users, provider)
    fake_models(monkeypatch, ModelPage([f"m{i}" for i in range(count)]))
    query = {"api_key_id": key_id}
    dynamic = client.get(BASE + "/models", params=query, headers=users["alice"][0])
    response = client.get(MONITOR_MODELS, params=query, headers=users["alice"][0])
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data == {
        "status": "ok",
        "source": "provider_api",
        "scope": "user_api_key",
        "live_provider_availability_checked": True,
        "providers": [
            {"provider": provider, "models": [f"m{i}" for i in range(count)], "complete": complete}
        ],
    }
    assert dynamic.json()["data"]["source"] == data["source"]
    assert dynamic.json()["data"]["scope"] == data["scope"]
    assert response.headers["cache-control"] == "no-store"
    assert key_id not in response.text and MODEL_SECRET not in response.text


@pytest.mark.parametrize(
    "state,status",
    [
        ("missing", 404),
        ("other", 404),
        ("deleted", 404),
        ("anonymous", 401),
        ("regular", 403),
        ("empty", 400),
    ],
)
def test_monitor_models_rejects_invalid_access_before_provider(api, monkeypatch, state, status):
    app, client, users = api
    make_model_admin(app, users)
    key_id = model_key(app, users)
    if state == "other":
        from uuid import UUID

        app.state.monitor.settings.MONITOR_ADMIN_USER_IDS = [UUID(users["bob"][1])]
    if state == "deleted":
        app.state.auth.delete_key(key_id, users["alice"][1])
    sdk, configs = fake_models(monkeypatch, AssertionError("must not query"))
    who = "bob" if state in ("other", "regular") else "alice"
    auth = {} if state == "anonymous" else users[who][0]
    query = {"api_key_id": "missing" if state == "missing" else "" if state == "empty" else key_id}
    response = client.get(MONITOR_MODELS, params=query, headers=auth)
    assert response.status_code == status, response.text
    assert response.headers["cache-control"] == "no-store"
    assert configs == []


@pytest.mark.parametrize("state,status", [("provider", 503), ("changed", 409), ("limit", 429)])
def test_monitor_models_errors_never_fall_back_to_static(api, monkeypatch, state, status):
    app, client, users = api
    make_model_admin(app, users)
    key_id = model_key(app, users)

    def changed():
        if state == "changed":
            app.state.auth.delete_key(key_id, users["alice"][1])

    sdk, configs = fake_models(
        monkeypatch,
        RuntimeError(MODEL_SECRET) if state == "provider" else ModelPage(["private-model"]),
        changed,
    )
    if state == "limit":
        app.state.auth.settings.AUTH_RATE_LIMIT = 1
        app.state.auth.limit("models:" + users["alice"][1])
    response = client.get(MONITOR_MODELS, params={"api_key_id": key_id}, headers=users["alice"][0])
    assert response.status_code == status, response.text
    assert MODEL_SECRET not in response.text and "private-model" not in response.text
    assert "static_examples" not in response.text
    assert response.headers["cache-control"] == "no-store"
    if state != "limit":
        assert sdk.closed is True
