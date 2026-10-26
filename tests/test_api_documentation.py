"""Catch undocumented operations and examples that disagree with wire contracts."""

import json

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from pydantic import TypeAdapter

from api.auth.dependencies import current_user
from api.auth.models import LoginInput, RegisterInput
from api.auth.service import KEY_FIELDS
from api.files.service import PUBLIC_FIELDS
from api.files.templates import template
from api.main import create_app
from api.middleware.errors import ErrorResponse
from api.models import EvaluationCreateRequest
from api.schemas import ApiResponse, EvaluationResponse


@pytest.fixture(scope="module")
def schema():
    # No lifespan: generating documentation must not need secrets, DB or Redis.
    return TestClient(create_app()).get("/openapi.json").json()


def test_every_http_operation_has_actionable_documentation(schema):
    operations = [(p, m, o) for p, methods in schema["paths"].items() for m, o in methods.items()]
    assert len(operations) >= 100
    for path, method, operation in operations:
        label = f"{method} {path}"
        description = operation.get("description", "")
        assert "认证" in description, label
        assert "速率限制" in description, label
        assert "curl " in description, label
        for parameter in operation.get("parameters", []):
            assert parameter.get("description"), (label, parameter["name"])
            assert "example" in parameter, (label, parameter["name"])
        for media in operation.get("requestBody", {}).get("content", {}).values():
            assert "example" in media or "examples" in media, label
        for status, response in operation["responses"].items():
            assert response.get("description"), (label, status)
            if status == "204":
                assert "content" not in response, label
            elif status.startswith("2"):
                assert response.get("content"), label
                for media in response["content"].values():
                    assert "example" in media or "examples" in media, label


def test_authentication_and_errors_match_runtime_contract(schema):
    paths = schema["paths"]
    assert not paths["/api/v1/health"]["get"].get("security")
    assert not paths["/api/v1/auth/login"]["post"].get("security")
    assert paths["/api/v1/users/me"]["get"]["security"] == [{"HTTPBearer": []}]
    assert "管理员" in paths["/api/v1/system/health"]["get"]["description"]
    response = paths["/api/v1/evaluations"]["post"]["responses"]["400"]
    assert (
        response["content"]["application/json"]["examples"]["INVALID_PARAMETER"]["value"]["error"][
            "code"
        ]
        == "INVALID_PARAMETER"
    )
    assert "Retry-After" in paths["/api/v1/users/me"]["get"]["responses"]["429"]["headers"]
    assert "422" not in paths["/api/v1/auth/register"]["post"]["responses"]


def test_container_resources_example_matches_disabled_probe(schema):
    from api.monitoring.config import MonitorSettings
    from api.monitoring.containers import ContainerProbes

    probe = ContainerProbes(
        MonitorSettings(
            _env_file=None,
            MONITOR_CONTAINER_PROBES_ENABLED=False,
            MONITOR_CONTAINER_TIMEOUT_SECONDS=3,
            MONITOR_CONTAINER_MAX_ITEMS=32,
        )
    )
    try:
        example = schema["paths"]["/api/v1/system/status"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["example"]
        assert example["data"]["containers"] == probe.read()
    finally:
        probe.close()


@pytest.mark.parametrize(
    ("path", "model"),
    [
        ("auth/register", RegisterInput),
        ("auth/login", LoginInput),
        ("evaluations", EvaluationCreateRequest),
    ],
)
def test_request_examples_validate_against_real_models(schema, path, model):
    example = schema["paths"][f"/api/v1/{path}"]["post"]["requestBody"]["content"][
        "application/json"
    ]["example"]
    model.model_validate(example)


def test_evaluation_response_example_validates(schema):
    example = schema["paths"]["/api/v1/evaluations"]["post"]["responses"]["201"]["content"][
        "application/json"
    ]["example"]
    TypeAdapter(ApiResponse[EvaluationResponse]).validate_python(example)


@pytest.mark.parametrize(
    "path,status,can_start,can_cancel",
    [
        ("/api/v1/evaluations", "201", True, False),
        ("/api/v1/evaluations/{evaluation_id}/start", "202", False, True),
        ("/api/v1/evaluations/{evaluation_id}/cancel", "200", False, False),
    ],
)
def test_evaluation_examples_describe_lifecycle_capabilities(
    schema, path, status, can_start, can_cancel
):
    example = schema["paths"][path]["post"]["responses"][status]["content"]["application/json"][
        "example"
    ]["data"]
    assert example["can_start"] is can_start
    assert example["can_cancel"] is can_cancel
    assert example["status"] == ("cancelled" if path.endswith("/cancel") else "pending")
    assert example["execution_progress"] == {
        "completed_units": 0,
        "total_units": 1,
        "percentage": 0.0,
    }


def test_all_json_examples_validate_against_route_models(schema):
    def routes(router):
        for route in router.routes:
            if isinstance(route, APIRoute):
                yield route
            elif hasattr(route, "original_router"):
                yield from routes(route.original_router)

    for route in routes(create_app()):
        for method in route.methods:
            operation = schema["paths"][route.path][method.lower()]
            if route.body_field is not None:
                example = operation["requestBody"]["content"]["application/json"]["example"]
                TypeAdapter(route.body_field.field_info.annotation).validate_python(example)
            status = str(route.status_code or 200)
            response = operation["responses"][status]
            if route.response_model and "application/json" in response.get("content", {}):
                TypeAdapter(route.response_model).validate_python(
                    response["content"]["application/json"]["example"]
                )
            for status, response in operation["responses"].items():
                if not status.startswith("2"):
                    for example in response["content"]["application/json"]["examples"].values():
                        response_model = route.responses.get(
                            int(status) if status.isdecimal() else status, {}
                        ).get("model", ErrorResponse)
                        TypeAdapter(response_model).validate_python(example["value"])


@pytest.mark.parametrize("path", ["pareto/analyze", "optimize"])
def test_stateless_analysis_response_examples_match_real_payloads(schema, path):
    app = create_app()
    app.dependency_overrides[current_user] = lambda: None
    operation = schema["paths"][f"/api/v1/{path}"]["post"]
    request = operation["requestBody"]["content"]["application/json"]["example"]
    response = TestClient(app).post(f"/api/v1/{path}", json=request)
    assert response.status_code == 200
    actual = response.json()["data"]
    documented = dict(
        operation["responses"]["200"]["content"]["application/json"]["example"]["data"]
    )
    actual.pop("generated_at", None)
    documented.pop("generated_at", None)
    assert actual == documented


def test_documented_metadata_fields_match_public_views(schema):
    paths = schema["paths"]
    key = paths["/api/v1/api-keys"]["post"]["responses"]["201"]["content"]["application/json"][
        "example"
    ]["data"]
    assert set(key) == set(KEY_FIELDS)
    file = paths["/api/v1/files/{file_id}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]["data"]
    assert set(file) == set(PUBLIC_FIELDS)
    example = paths["/api/v1/configs/templates/{name}"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["example"]["data"]
    assert example == template("vanilla")


@pytest.mark.parametrize("kind", ["redis", "workers"])
def test_queue_examples_match_disabled_probe_contract(schema, kind):
    from api.monitoring.config import MonitorSettings
    from api.monitoring.queue_health import QueueProbes

    queue = QueueProbes(
        MonitorSettings(
            _env_file=None,
            MONITOR_QUEUE_PROBES_ENABLED=False,
            MONITOR_QUEUE_TIMEOUT_SECONDS=3.0,
        ),
        "redis://unused:6379/0",
    )
    try:
        operation = schema["paths"][f"/api/v1/health/{kind}"]["get"]
        example = operation["responses"]["200"]["content"]["application/json"]["example"]
        assert example["data"] == queue.read(kind)
        assert "MONITOR_QUEUE_PROBES_ENABLED" in operation["description"]
    finally:
        queue.close()


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("reports/markdown/{run_id}", "text/markdown"),
        ("reports/html/{run_id}", "text/html"),
        ("reports/csv/{run_id}", "text/csv"),
        ("logs/download/{task_id}", "text/plain"),
        ("results/{run_id}/charts/{chart_name}", "image/png"),
    ],
)
def test_downloads_are_not_documented_as_json_envelopes(schema, path, media_type):
    response = schema["paths"][f"/api/v1/{path}"]["get"]["responses"]["200"]
    assert set(response["content"]) == {media_type}
    assert "Content-Disposition" in response["headers"]


def test_docs_pages_and_schema_are_public_without_startup_secrets():
    http = TestClient(create_app())
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert http.get(path).status_code == 200
    schema = http.get("/openapi.json").json()
    assert "WebSocket" in schema["info"]["description"]
    assert "/api/v1/ws/progress" not in schema["paths"]
    assert json.loads(json.dumps(schema)) == schema
