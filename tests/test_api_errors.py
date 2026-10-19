"""HTTP error contract across handlers, framework errors and early boundaries."""

import asyncio
import logging
import secrets
from concurrent.futures import ThreadPoolExecutor

import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from api.auth.config import AuthSettings
from api.files.config import FileSettings
from api.main import create_app
from api.middleware.errors import (
    ApiError,
    ConflictError,
    ErrorBoundaryMiddleware,
    ValidationApiError,
    setup_error_handlers,
)
from api.middleware.logging import setup_logging_middleware


class Input(BaseModel):
    count: int = Field(ge=1)
    password: str = Field(default="", min_length=8)


@pytest.fixture
def client():
    app = FastAPI()
    setup_logging_middleware(app)
    setup_error_handlers(app)

    @app.get("/failure/{status}")
    def failure(status: int):
        raise HTTPException(status, "Request rejected", headers={"Retry-After": "7"})

    @app.post("/validated")
    def validated(body: Input):
        return {"count": body.count}

    @app.get("/business")
    def business():
        raise ApiError("Budget exhausted", error_code="BUDGET_EXCEEDED", status_code=400)

    @app.get("/conflict")
    def conflict():
        raise ConflictError("Resource already exists")

    @app.get("/structured")
    def structured():
        raise HTTPException(400, {"message": "Invalid rows", "errors": {"row": "missing"}})

    @app.get("/secret-detail")
    def secret_detail():
        raise HTTPException(
            400, {"message": "Invalid configuration", "api_key": "private-input-123"}
        )

    @app.get("/custom-validation")
    def custom_validation():
        raise ValidationApiError("Invalid count", {"count": "must be positive"})

    @app.get("/crash")
    def crash():
        raise RuntimeError("private-provider-token-123")

    @app.get("/private-failure")
    def private_failure():
        raise HTTPException(503, "private-provider-token-123")

    @app.get("/bad-response", response_model=int)
    def bad_response():
        return {"password": "private-provider-token-123"}

    with TestClient(app, raise_server_exceptions=False) as http:
        yield http


def error(response, status, code):
    assert response.status_code == status, response.text
    body = response.json()
    assert body["success"] is False
    payload = body["error"]
    assert payload["code"] == code
    assert isinstance(payload["message"], str) and payload["message"]
    assert "details" in payload
    assert payload["request_id"].startswith("req_")
    assert response.headers["X-Request-ID"] == payload["request_id"]
    assert body["message"] == payload["message"]
    return body


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (400, "INVALID_PARAMETER"),
        (401, "UNAUTHORIZED"),
        (403, "FORBIDDEN"),
        (404, "RESOURCE_NOT_FOUND"),
        (408, "REQUEST_TIMEOUT"),
        (409, "DUPLICATE_RESOURCE"),
        (413, "PAYLOAD_TOO_LARGE"),
        (415, "UNSUPPORTED_MEDIA_TYPE"),
        (429, "RATE_LIMIT_EXCEEDED"),
        (500, "INTERNAL_ERROR"),
        (503, "SERVICE_UNAVAILABLE"),
    ],
)
def test_http_error_codes_and_headers(client, status, code):
    response = client.get(f"/failure/{status}")
    body = error(response, status, code)
    assert response.headers["Retry-After"] == "7"
    if status < 500:
        assert body["detail"] == "Request rejected"


def test_framework_not_found_and_method_not_allowed(client):
    error(client.get("/missing"), 404, "RESOURCE_NOT_FOUND")
    response = client.post("/business")
    error(response, 405, "METHOD_NOT_ALLOWED")
    assert "GET" in response.headers["Allow"]


def test_validation_preserves_field_details_without_echoing_input(client):
    response = client.post("/validated", json={"count": 0, "password": "private-input-123"})
    body = error(response, 400, "INVALID_PARAMETER")
    assert "count" in body["error"]["details"]
    assert body["details"] == body["error"]["details"]
    assert "private-input-123" not in response.text


def test_explicit_business_code_and_conflict_status(client):
    error(client.get("/business"), 400, "BUDGET_EXCEEDED")
    error(client.get("/conflict"), 409, "DUPLICATE_RESOURCE")


def test_structured_detail_remains_compatible(client):
    body = error(client.get("/structured"), 400, "INVALID_PARAMETER")
    assert body["detail"] == {"message": "Invalid rows", "errors": {"row": "missing"}}
    assert body["error"]["message"] == "Invalid rows"
    assert body["error"]["details"] == {"errors": {"row": "missing"}}


def test_validation_messages_for_credential_fields_remain_useful(client):
    response = client.post("/validated", json={"count": 1, "password": "short"})
    body = error(response, 400, "INVALID_PARAMETER")
    assert "at least 8" in body["details"]["password"]
    assert "short" not in response.text


def test_explicit_validation_and_sensitive_http_detail(client):
    body = error(client.get("/custom-validation"), 400, "INVALID_PARAMETER")
    assert body["details"] == {"count": "must be positive"}
    response = client.get("/secret-detail")
    error(response, 400, "INVALID_PARAMETER")
    assert "private-input-123" not in response.text


@pytest.mark.parametrize("path", ["/crash", "/bad-response", "/private-failure"])
def test_internal_failures_do_not_leak_private_data(client, caplog, path):
    with caplog.at_level(logging.ERROR, logger="api.middleware.errors"):
        response = client.get(path)
    error(
        response,
        503 if path == "/private-failure" else 500,
        "SERVICE_UNAVAILABLE" if path == "/private-failure" else "INTERNAL_ERROR",
    )
    assert "private-provider-token-123" not in response.text + caplog.text
    if path != "/private-failure":
        assert response.json()["error"]["request_id"] in caplog.text


def test_internal_failure_does_not_escape_to_server_traceback_logging(client):
    # Starlette normally re-raises after sending its 500 response. A production
    # server would then log the original exception, including provider secrets.
    with TestClient(client.app, raise_server_exceptions=True) as strict:
        response = strict.get("/crash")
    error(response, 500, "INTERNAL_ERROR")


def test_stream_failure_after_headers_is_not_rewritten_as_another_response():
    messages = []

    async def stream(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"partial", "more_body": True})
        raise RuntimeError("stream failed")

    async def receive():
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    with pytest.raises(RuntimeError, match="stream failed"):
        asyncio.run(ErrorBoundaryMiddleware(stream)({"type": "http"}, receive, send))
    assert [item["status"] for item in messages if item["type"] == "http.response.start"] == [200]
    assert messages[-1]["body"] == b"partial"


def test_request_ids_are_server_generated_and_isolated(client):
    def request(_):
        response = client.get("/missing", headers={"X-Request-ID": "untrusted-private-id"})
        return error(response, 404, "RESOURCE_NOT_FOUND")["error"]["request_id"]

    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(request, range(8)))
    assert len(set(ids)) == 8
    assert "untrusted-private-id" not in ids
    response = client.post("/validated", json={"count": 1})
    assert response.json() == {"count": 1}
    assert response.headers["X-Request-ID"].startswith("req_")


@pytest.fixture
def api(tmp_path):
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=50,
    )
    files = FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads")
    app = create_app(auth, files)
    with TestClient(app, raise_server_exceptions=False) as http:
        yield http, app


def test_missing_and_invalid_tokens_in_routes_and_upload_boundary(api):
    client, _ = api
    for path in ("/api/v1/users/me", "/api/v1/files/upload"):
        send = client.post if path.endswith("upload") else client.get
        missing = send(path)
        error(missing, 401, "UNAUTHORIZED")
        invalid = send(path, headers={"Authorization": "Bearer invalid-token"})
        error(invalid, 401, "INVALID_TOKEN")
        assert (
            missing.headers["WWW-Authenticate"] == invalid.headers["WWW-Authenticate"] == "Bearer"
        )
        assert missing.headers["Cache-Control"] == "no-store"


def test_auth_body_limit_uses_error_contract(api):
    client, _ = api
    response = client.post("/api/v1/auth/register", content=b"x" * 17000)
    error(response, 413, "PAYLOAD_TOO_LARGE")
    assert response.headers["Cache-Control"] == "no-store"


def test_rejected_cors_preflight_is_a_json_error_without_weakening_policy(api):
    client, _ = api
    response = client.options(
        "/api/v1/users/me",
        headers={
            "Origin": "https://unapproved.example",
            "Access-Control-Request-Method": "GET",
        },
    )
    error(response, 400, "INVALID_PARAMETER")
    assert "Access-Control-Allow-Origin" not in response.headers
    origin = "http://localhost:3000"
    response = client.options(
        "/api/v1/users/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "TRACE",
        },
    )
    error(response, 400, "INVALID_PARAMETER")
    assert response.headers["Access-Control-Allow-Origin"] == origin
    assert "TRACE" not in response.headers["Access-Control-Allow-Methods"]
    allowed = client.options(
        "/api/v1/users/me",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert allowed.status_code == 200


def test_unexpected_route_and_upload_boundary_failures_have_cors_and_no_store(api, monkeypatch):
    client, app = api

    def crash():
        raise RuntimeError("private-provider-token-123")

    app.add_api_route("/api/v1/crash", crash, methods=["GET"])
    origin = {"Origin": "http://localhost:3000"}
    monkeypatch.setattr(app.state.auth, "authenticate", lambda token: crash())
    strict = TestClient(app, raise_server_exceptions=True)
    try:
        for response in (
            strict.get("/api/v1/crash", headers=origin),
            strict.post(
                "/api/v1/files/upload", headers={**origin, "Authorization": "Bearer token"}
            ),
        ):
            error(response, 500, "INTERNAL_ERROR")
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Access-Control-Allow-Origin"] == origin["Origin"]
            assert "private-provider-token-123" not in response.text
    finally:
        strict.close()


def test_upload_capacity_size_and_length_errors_preserve_headers(api):
    client, app = api
    password = "private-long-password!"
    assert (
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "errors",
                "email": "errors@example.org",
                "password": password,
            },
        ).status_code
        == 201
    )
    token = client.post(
        "/api/v1/auth/login",
        json={
            "username": "errors",
            "password": password,
        },
    ).json()["data"]["access_token"]
    headers = {"Authorization": "Bearer " + token, "Origin": "http://localhost:3000"}
    service = app.state.files
    count = service.settings.FILE_MAX_CONCURRENT_TRANSFERS
    for _ in range(count):
        assert service.transfers.acquire(blocking=False)
    try:
        response = client.post("/api/v1/files/upload", headers=headers)
        error(response, 429, "RATE_LIMIT_EXCEEDED")
        assert response.headers["Retry-After"] == "1"
        assert response.headers["Access-Control-Allow-Origin"] == headers["Origin"]
    finally:
        for _ in range(count):
            service.transfers.release()
    response = client.post(
        "/api/v1/files/upload", headers={**headers, "Content-Length": "invalid"}, content=b"{}"
    )
    error(response, 400, "INVALID_PARAMETER")
    service.settings.FILE_UPLOAD_MAX_BYTES = 1
    response = client.post("/api/v1/files/upload", headers=headers, content=b"x" * 70000)
    error(response, 413, "PAYLOAD_TOO_LARGE")
    assert response.headers["Cache-Control"] == "no-store"


def test_login_rate_limit_and_refresh_errors(api):
    client, app = api
    app.state.auth.settings.AUTH_RATE_LIMIT = 1
    response = client.post(
        "/api/v1/auth/login", json={"username": "missing", "password": "wrong-password"}
    )
    error(response, 401, "UNAUTHORIZED")
    response = client.post(
        "/api/v1/auth/login", json={"username": "missing", "password": "wrong-password"}
    )
    error(response, 429, "RATE_LIMIT_EXCEEDED")
    assert int(response.headers["Retry-After"]) >= 1
    app.state.auth.settings.AUTH_RATE_LIMIT = 50
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
    error(response, 401, "INVALID_TOKEN")


def test_openapi_error_contract_matches_validation_status(api):
    client, _ = api
    spec = client.get("/openapi.json").json()
    responses = spec["paths"]["/api/v1/auth/register"]["post"]["responses"]
    assert "400" in responses and "422" not in responses
    ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
    model = spec["components"]["schemas"][ref.rsplit("/", 1)[1]]
    assert "error" in model["properties"]
    enums = [schema.get("enum", []) for schema in spec["components"]["schemas"].values()]
    assert any("INVALID_PARAMETER" in values and "INTERNAL_ERROR" in values for values in enums)
