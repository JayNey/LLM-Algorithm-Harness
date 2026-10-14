"""Real HTTP + SQLite tests for identity, ownership, persistence and abuse boundaries."""

import secrets
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock, patch

import jwt
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.auth.config import AuthSettings
from api.auth.service import PROVIDER_URLS, AuthService
from api.auth.store import AuthStore
from api.files.config import FileSettings
from api.main import create_app

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"


def config(tmp_path, **kwargs):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=kwargs.pop("AUTH_RATE_LIMIT", 100),
        **kwargs,
    )


def signup(client, name="alice"):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.org", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def headers(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def add_key(client, tokens, provider="openai", raw=KEY):
    response = client.post(
        "/api/v1/api-keys",
        headers=headers(tokens),
        json={"provider": provider, "key_name": "test", "api_key": raw},
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["id"]


@pytest.fixture
def api(tmp_path):
    settings = config(tmp_path)
    app = create_app(
        settings,
        FileSettings(_env_file=None, UPLOAD_DIR=settings.AUTH_DATABASE_PATH.parent / "uploads"),
    )
    with TestClient(app) as client:
        tokens = signup(client)
        yield client, tokens, app, settings


def test_register_login_profile_and_no_plaintext_password(api):
    client, tokens, app, settings = api
    me = client.get("/api/v1/users/me", headers=headers(tokens))
    assert me.status_code == 200
    assert me.json()["data"]["username"] == "alice"
    assert "password" not in me.text
    user = app.state.auth.store.find_user("alice")
    assert user["password_hash"].startswith("$argon2id$")
    assert PASSWORD.encode() not in settings.AUTH_DATABASE_PATH.read_bytes()
    assert (
        client.patch(
            "/api/v1/users/me",
            headers=headers(tokens),
            json={"username": "Alice_New", "email": "new@example.org"},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "NEW@example.org", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert me.headers["cache-control"] == "no-store"
    assert "set-cookie" not in me.headers


@pytest.mark.parametrize("identity", ["alice", "missing", "alice' OR 1=1 --"])
def test_bad_login_is_generic_and_injection_safe(api, identity):
    client, _, _, _ = api
    response = client.post("/api/v1/auth/login", json={"username": identity, "password": "wrong"})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["detail"] == "Invalid or expired credentials"


def test_duplicate_profiles_are_case_insensitive(api):
    client, tokens, _, _ = api
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"username": "ALICE", "email": "other@example.org", "password": PASSWORD},
        ).status_code
        == 409
    )
    other = signup(client, "bob")
    assert (
        client.patch(
            "/api/v1/users/me", headers=headers(other), json={"email": "ALICE@example.org"}
        ).status_code
        == 409
    )
    assert (
        client.get("/api/v1/users/me", headers=headers(tokens)).json()["data"]["email"]
        == "alice@example.org"
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"username": "alice", "email": "x@example.org", "password": "short"},
        {"username": "<script>", "email": "x@example.org", "password": PASSWORD},
        {"username": "new", "email": "bad", "password": PASSWORD},
        {"username": "new", "email": "x@example.org", "password": PASSWORD, "role": "admin"},
    ],
)
def test_registration_validation_does_not_echo_secrets(api, payload):
    client, _, _, _ = api
    response = client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400
    assert payload["password"] not in response.text


def test_refresh_rotation_and_logout_persist_after_restart(api):
    client, old, _, settings = api
    refreshed = client.post("/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]})
    assert refreshed.status_code == 200
    new = refreshed.json()["data"]
    assert new["refresh_token"] != old["refresh_token"]
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": old["refresh_token"]}
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/auth/refresh", json={"refresh_token": old["access_token"]}).status_code
        == 401
    )
    assert client.post("/api/v1/auth/logout", headers=headers(new)).status_code == 204
    with TestClient(
        create_app(
            settings,
            FileSettings(_env_file=None, UPLOAD_DIR=settings.AUTH_DATABASE_PATH.parent / "uploads"),
        )
    ) as restarted:
        assert restarted.get("/api/v1/users/me", headers=headers(old)).status_code == 401
        assert restarted.get("/api/v1/users/me", headers=headers(new)).status_code == 401
        assert (
            restarted.post(
                "/api/v1/auth/refresh", json={"refresh_token": new["refresh_token"]}
            ).status_code
            == 401
        )
        # Separate login sessions survive logout of the first session.
        login = restarted.post(
            "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
        )
        assert (
            restarted.get("/api/v1/users/me", headers=headers(login.json()["data"])).status_code
            == 200
        )


def test_refresh_race_has_only_one_winner_across_services(api):
    _, tokens, app, settings = api
    services = [app.state.auth, AuthService(settings)]

    def attempt(service):
        try:
            return service.refresh(tokens["refresh_token"])
        except HTTPException as exc:
            return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(attempt, services))
    assert sum(isinstance(value, dict) for value in result) == 1
    assert 401 in result


@pytest.mark.parametrize(
    "change",
    [
        {"exp": 1},
        {"type": "refresh"},
        {"aud": "other"},
        {"iss": "other"},
        {"sid": "unknown"},
        {"sub": "unknown"},
        {"nbf": int(time.time()) + 3600},
        {"iat": int(time.time()) + 3600},
        {"jti": ""},
        {"exp": "bad"},
        {"sid": 1},
    ],
)
def test_invalid_claims_rejected(api, change):
    client, tokens, _, settings = api
    claims = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    claims.update(change)
    token = jwt.encode(claims, settings.SECRET_KEY.get_secret_value(), algorithm="HS256")
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


@pytest.mark.parametrize("mode", ["wrong-secret", "missing-claim", "none", "malformed", "oversize"])
def test_jwt_tampering_rejected(api, mode):
    client, tokens, _, settings = api
    claims = jwt.decode(tokens["access_token"], options={"verify_signature": False})
    secret = settings.SECRET_KEY.get_secret_value()
    if mode == "missing-claim":
        del claims["jti"]
    if mode == "none":
        token = jwt.encode(claims, key=None, algorithm="none")
    elif mode == "malformed":
        token = "not-a-jwt"
    elif mode == "oversize":
        token = "x" * 5000
    else:
        token = jwt.encode(
            claims, "wrong" * 12 if mode == "wrong-secret" else secret, algorithm="HS256"
        )
    assert (
        client.get("/api/v1/users/me", headers={"Authorization": "Bearer " + token}).status_code
        == 401
    )


def test_cookie_and_query_tokens_are_not_authentication(api):
    client, tokens, _, _ = api
    assert (
        client.get(
            "/api/v1/users/me",
            params={"token": tokens["access_token"]},
            headers={"Cookie": "access_token=" + tokens["access_token"]},
        ).status_code
        == 401
    )
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/docs").status_code == 200
    spec = client.get("/openapi.json").json()
    assert "HTTPBearer" in spec["components"]["securitySchemes"]


def test_keys_encrypted_isolated_editable_and_survive_restart(api, caplog):
    client, tokens, app, settings = api
    bob = signup(client, "bob")
    key_id = add_key(client, tokens)
    alice = app.state.auth.store.find_user("alice")
    stored = app.state.auth.store.key(key_id, alice["id"])
    assert stored["ciphertext"] != KEY
    assert (
        Fernet(settings.ENCRYPTION_KEY.get_secret_value())
        .decrypt(stored["ciphertext"].encode())
        .decode()
        == KEY
    )
    assert KEY.encode() not in settings.AUTH_DATABASE_PATH.read_bytes()
    listed = client.get("/api/v1/api-keys", headers=headers(tokens))
    assert KEY not in listed.text and "ciphertext" not in listed.text
    assert client.get("/api/v1/api-keys", headers=headers(bob)).json()["data"] == []
    for method, suffix, body in [
        ("patch", "", {"key_name": "stolen"}),
        ("delete", "", None),
        ("post", "/verify", None),
    ]:
        assert (
            client.request(
                method, f"/api/v1/api-keys/{key_id}{suffix}", headers=headers(bob), json=body
            ).status_code
            == 404
        )
    edited = client.patch(
        f"/api/v1/api-keys/{key_id}",
        headers=headers(tokens),
        json={"api_key": "replacement-secret", "key_name": "updated"},
    )
    assert edited.status_code == 200 and "replacement-secret" not in edited.text
    with TestClient(
        create_app(
            settings,
            FileSettings(_env_file=None, UPLOAD_DIR=settings.AUTH_DATABASE_PATH.parent / "uploads"),
        )
    ) as restarted:
        assert (
            restarted.get("/api/v1/api-keys", headers=headers(tokens)).json()["data"][0]["key_name"]
            == "updated"
        )
    assert client.delete(f"/api/v1/api-keys/{key_id}", headers=headers(tokens)).status_code == 204
    assert (
        client.patch(
            f"/api/v1/api-keys/{key_id}", headers=headers(tokens), json={"key_name": "x"}
        ).status_code
        == 404
    )
    assert KEY not in caplog.text and PASSWORD not in caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        {"provider": "local", "key_name": "x", "api_key": KEY},
        {"provider": "openai", "key_name": "x", "api_key": "ENV:SECRET_KEY"},
        {"provider": "openai", "key_name": "x", "api_key": KEY, "base_url": "http://127.0.0.1/"},
        {"provider": "openai", "key_name": "x", "api_key": "bad\nkey"},
        {"provider": "openai", "key_name": "x", "api_key": " "},
    ],
)
def test_key_input_rejects_server_env_and_arbitrary_endpoints(api, payload):
    client, tokens, _, _ = api
    response = client.post("/api/v1/api-keys", headers=headers(tokens), json=payload)
    assert response.status_code == 400
    assert KEY not in response.text


@pytest.mark.parametrize("provider", ["openai", "anthropic", "siliconflow"])
@pytest.mark.parametrize("ok", [True, False])
def test_provider_check_is_bounded_sanitized_and_counted(api, monkeypatch, caplog, provider, ok):
    client, tokens, app, _ = api
    key_id = add_key(client, tokens, provider=provider)
    captured = []
    fake = Mock()
    fake.client.with_options.return_value = fake.client
    fake.check_connection.return_value = {"ok": ok, "error": KEY, "base_url": KEY}

    def construct(configuration):
        captured.append(configuration)
        return fake

    monkeypatch.setattr("api.auth.service.LLMClient", construct)
    response = client.post(f"/api/v1/api-keys/{key_id}/verify", headers=headers(tokens))
    assert response.status_code == 200
    assert response.json()["data"]["ok"] is ok
    assert KEY not in response.text and KEY not in caplog.text
    conf = captured[0]
    assert conf.provider == provider and conf.api_key.get_secret_value() == KEY
    assert conf.base_url is None and conf.timeout == 5 and conf.retry_max_attempts == 1
    assert conf.cache.enabled is False
    fake.client.with_options.assert_called_once_with(
        timeout=5.0, max_retries=0, base_url=PROVIDER_URLS[provider]
    )
    fake.check_connection.assert_called_once()
    fake.generate.assert_not_called()
    fake.client.close.assert_called_once()
    metadata = client.get("/api/v1/api-keys", headers=headers(tokens)).json()["data"][0]
    assert metadata["verification_count"] == 1 and metadata["verified"] == int(ok)
    assert metadata["usage_count"] == 0
    alice = app.state.auth.store.find_user("alice")
    app.state.auth.store.record_key_usage(key_id, alice["id"])
    metadata = client.get("/api/v1/api-keys", headers=headers(tokens)).json()["data"][0]
    assert metadata["usage_count"] == 1 and metadata["last_used_at"] is not None


def test_provider_exceptions_and_wrong_encryption_key_do_not_leak(api, monkeypatch, caplog):
    client, tokens, app, settings = api
    key_id = add_key(client, tokens)
    monkeypatch.setattr("api.auth.service.LLMClient", Mock(side_effect=RuntimeError(KEY)))
    result = client.post(f"/api/v1/api-keys/{key_id}/verify", headers=headers(tokens))
    assert result.json()["data"]["ok"] is False
    assert KEY not in result.text + caplog.text
    alice = app.state.auth.store.find_user("alice")
    app.state.auth._fernet = Fernet(Fernet.generate_key())
    with pytest.raises(HTTPException) as failure:
        app.state.auth.llm_config(key_id, alice["id"], "test-model")
    assert failure.value.status_code == 503
    assert KEY not in str(failure.value)


def test_verification_does_not_mark_concurrently_replaced_key_valid(api, monkeypatch):
    client, tokens, app, _ = api
    key_id = add_key(client, tokens)
    fake = Mock()
    fake.client.with_options.return_value = fake.client

    def check():
        assert (
            client.patch(
                f"/api/v1/api-keys/{key_id}",
                headers=headers(tokens),
                json={"api_key": "new-credential"},
            ).status_code
            == 200
        )
        return {"ok": True}

    fake.check_connection.side_effect = check
    monkeypatch.setattr("api.auth.service.LLMClient", Mock(return_value=fake))
    assert (
        client.post(f"/api/v1/api-keys/{key_id}/verify", headers=headers(tokens)).status_code == 200
    )
    record = client.get("/api/v1/api-keys", headers=headers(tokens)).json()["data"][0]
    assert record["verified"] == 0


@pytest.mark.parametrize(
    "method,suffix,body",
    [
        ("get", "", None),
        ("patch", "", {"budget_cap_usd": 1}),
        ("delete", "", None),
        ("post", "/start", None),
        ("post", "/cancel", None),
        ("get", "/progress", None),
    ],
)
def test_every_evaluation_operation_checks_ownership(api, method, suffix, body):
    client, alice, _, _ = api
    bob = signup(client, "bob")
    key_id = add_key(client, alice)
    response = client.post(
        "/api/v1/evaluations",
        headers=headers(alice),
        json={
            "problem_ids": ["1"],
            "strategy_names": ["vanilla"],
            "api_key_id": key_id,
            "model": "gpt-4o-mini",
        },
    )
    assert response.status_code == 201
    task_id = response.json()["data"]["evaluation_id"]
    url = f"/api/v1/evaluations/{task_id}{suffix}"
    assert client.request(method, url, headers=headers(bob), json=body).status_code == 404
    assert client.request(method, url, json=body).status_code == 401
    assert client.get("/api/v1/evaluations", headers=headers(bob)).json()["data"]["total"] == 0
    assert client.get("/api/v1/evaluations", headers=headers(alice)).json()["data"]["total"] == 1


def test_evaluation_cannot_use_other_users_or_deleted_keys(api):
    client, alice, _, _ = api
    bob = signup(client, "bob")
    key_id = add_key(client, alice)
    payload = {
        "problem_ids": ["1"],
        "strategy_names": ["vanilla"],
        "api_key_id": key_id,
        "model": "gpt-4o-mini",
    }
    assert client.post("/api/v1/evaluations", headers=headers(bob), json=payload).status_code == 404
    task_id = client.post("/api/v1/evaluations", headers=headers(alice), json=payload).json()[
        "data"
    ]["evaluation_id"]
    assert client.delete(f"/api/v1/api-keys/{key_id}", headers=headers(alice)).status_code == 204
    assert (
        client.post(f"/api/v1/evaluations/{task_id}/start", headers=headers(alice)).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/evaluations/{task_id}", headers=headers(alice)).json()["data"][
            "status"
        ]
        == "pending"
    )


def test_owner_evaluation_lifecycle(api):
    client, tokens, app, _ = api
    key_id = add_key(client, tokens)
    response = client.post(
        "/api/v1/evaluations",
        headers=headers(tokens),
        json={
            "problem_ids": ["1"],
            "strategy_names": ["vanilla"],
            "api_key_id": key_id,
            "model": "gpt-4o-mini",
        },
    )
    task_id = response.json()["data"]["evaluation_id"]
    url = f"/api/v1/evaluations/{task_id}"
    assert (
        client.patch(url, headers=headers(tokens), json={"budget_cap_usd": 10}).status_code == 200
    )
    # 启动只入队：交给 Celery worker 执行，worker 接管前评估保持 pending
    with patch("src.task_manager.celery_app.send_task", return_value=Mock()) as mock_send:
        assert client.post(url + "/start", headers=headers(tokens)).status_code == 202
    mock_send.assert_called_once()
    assert client.get(url, headers=headers(tokens)).json()["data"]["status"] == "pending"
    # 已入队的评估不能重复启动
    assert client.post(url + "/start", headers=headers(tokens)).status_code == 400
    assert client.delete(url, headers=headers(tokens)).status_code == 204
    assert client.get(url, headers=headers(tokens)).status_code == 404


def test_rate_limits_persist_and_ignore_spoofed_forwarded_headers(tmp_path):
    settings = config(tmp_path, AUTH_RATE_LIMIT=2)
    for _ in range(2):
        with TestClient(
            create_app(
                settings,
                FileSettings(
                    _env_file=None, UPLOAD_DIR=settings.AUTH_DATABASE_PATH.parent / "uploads"
                ),
            )
        ) as client:
            result = client.post(
                "/api/v1/auth/login",
                headers={"X-Forwarded-For": secrets.token_hex(8)},
                json={"username": "missing", "password": "bad"},
            )
            assert result.status_code == 401
    with TestClient(
        create_app(
            settings,
            FileSettings(_env_file=None, UPLOAD_DIR=settings.AUTH_DATABASE_PATH.parent / "uploads"),
        )
    ) as client:
        result = client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "other"},
            json={"username": "missing", "password": "bad"},
        )
        assert result.status_code == 429
        assert int(result.headers["retry-after"]) > 0


def test_rate_limit_atomic_across_store_instances_and_expiry(tmp_path):
    path = tmp_path / "auth.sqlite3"
    stores = [AuthStore(path), AuthStore(path)]
    with ThreadPoolExecutor(max_workers=10) as pool:
        allowed = list(pool.map(lambda i: stores[i % 2].allow("bucket", 3, 60)[0], range(10)))
    assert sum(allowed) == 3
    with stores[0].connection() as db:
        db.execute("UPDATE auth_rates SET expires_at=1")
    assert stores[1].allow("bucket", 3, 60)[0]


def test_protected_and_verification_rate_limits(api, monkeypatch):
    client, tokens, app, _ = api
    key_id = add_key(client, tokens)
    monkeypatch.setattr(
        "api.auth.service.LLMClient", Mock(side_effect=RuntimeError("offline check"))
    )
    app.state.auth.settings.AUTH_RATE_LIMIT = 1
    app.state.auth.verify_key(key_id, app.state.auth.store.find_user("alice")["id"])
    # The prior direct check may fail connectivity, but still consumes quota.
    assert (
        client.post(f"/api/v1/api-keys/{key_id}/verify", headers=headers(tokens)).status_code == 429
    )
    app.state.auth.settings.AUTH_PROTECTED_RATE_LIMIT = 1
    assert client.get("/api/v1/users/me", headers=headers(tokens)).status_code == 429


def test_body_limit_before_json_parse_including_chunked_input(api):
    client, _, _, _ = api
    for body in [b"x" * 17000, iter([b"x" * 9000, b"x" * 9000])]:
        result = client.post(
            "/api/v1/auth/login", content=body, headers={"Content-Type": "application/json"}
        )
        assert result.status_code == 413
    result = client.post(
        "/api/v1/auth/login", content="{", headers={"Content-Type": "application/json"}
    )
    assert result.status_code == 400


def test_missing_and_invalid_secret_configuration_fails_closed(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(ValidationError):
        AuthSettings(_env_file=None)
    with pytest.raises(ValidationError) as exc:
        AuthSettings(_env_file=None, SECRET_KEY="short", ENCRYPTION_KEY="invalid-secret-material")
    assert "invalid-secret-material" not in str(exc.value)
    assert "input_value" not in str(exc.value)


@pytest.mark.parametrize(
    "reference", ["env:SERVER_KEY", "${SERVER_KEY}", "ENV:SERVER_KEY", "Env:SERVER_KEY"]
)
def test_no_api_path_can_use_server_environment_credentials(api, monkeypatch, reference):
    client, tokens, app, _ = api
    monkeypatch.setenv("SERVER_KEY", "private-server-credential")
    constructor = Mock()
    monkeypatch.setattr("api.auth.service.LLMClient", constructor)
    response = client.post(
        "/api/v1/api-keys",
        headers=headers(tokens),
        json={"provider": "openai", "key_name": "x", "api_key": reference},
    )
    assert response.status_code == 400
    key_id = add_key(client, tokens)
    assert (
        client.patch(
            f"/api/v1/api-keys/{key_id}", headers=headers(tokens), json={"api_key": reference}
        ).status_code
        == 400
    )
    # An imported old record must fail closed at the internal worker boundary.
    owner = app.state.auth.store.find_user("alice")["id"]
    ciphertext = app.state.auth._fernet.encrypt(reference.encode()).decode()
    app.state.auth.store.update_key(key_id, owner, None, ciphertext)
    with pytest.raises(HTTPException) as failure:
        app.state.auth.llm_config(key_id, owner, "test-model")
    assert failure.value.status_code == 503
    response = client.post(f"/api/v1/api-keys/{key_id}/verify", headers=headers(tokens))
    assert response.json()["data"]["ok"] is False
    assert "private-server-credential" not in response.text
    constructor.assert_not_called()


def test_shared_dotenv_accepts_both_api_and_auth_settings(tmp_path):
    from api.config import Settings

    path = tmp_path / ".env"
    secret = secrets.token_urlsafe(48)
    encryption = Fernet.generate_key().decode()
    path.write_text(
        f"SECRET_KEY={secret}\nENCRYPTION_KEY={encryption}\nAPI_PORT=8000\n", encoding="utf-8"
    )
    assert Settings(_env_file=path).PORT == 8000
    auth = AuthSettings(_env_file=path)
    assert auth.SECRET_KEY.get_secret_value() == secret


def test_db_session_expiration_is_enforced_even_with_valid_jwt(api):
    client, tokens, app, _ = api
    with app.state.auth.store.connection() as db:
        db.execute("UPDATE auth_sessions SET expires_at=1")
    assert client.get("/api/v1/users/me", headers=headers(tokens)).status_code == 401
    assert (
        client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        ).status_code
        == 401
    )
