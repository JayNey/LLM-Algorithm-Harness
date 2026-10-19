"""Version discovery and the frozen v1 HTTP contract used by the normal CI suite."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import create_app

BASELINE = Path(__file__).parent / "fixtures" / "openapi-v1.json"


@pytest.fixture(scope="module")
def schema():
    return create_app().openapi()


def test_api_contract_version_is_visible_in_public_documentation(schema):
    assert schema["info"]["version"] == "1.0.0"
    assert "/api/v1" in schema["info"]["description"]
    assert "Header" in schema["info"]["description"]
    for path, methods in schema["paths"].items():
        assert path.startswith("/api/v1/"), path
        for operation in methods.values():
            assert "API v1" in operation["description"], path


def test_url_version_and_release_version_remain_independent():
    client = TestClient(create_app())
    response = client.get("/api/v1/health", headers={"API-Version": "2"})
    assert response.status_code == 200
    assert response.json()["data"]["version"] == "0.1.0"
    assert client.get("/api/v2/health").status_code == 404
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 200


# Names inside these maps belong to the API author, even if they are called
# 'description' or 'example'. Never treat those names as documentation keys.
NAME_MAPS = {
    "paths",
    "properties",
    "schemas",
    "securitySchemes",
    "responses",
    "content",
    "headers",
    "encoding",
    "links",
    "callbacks",
    "$defs",
    "patternProperties",
    "dependentSchemas",
    "mapping",
}
ANNOTATIONS = {
    "description",
    "summary",
    "title",
    "example",
    "examples",
    "externalDocs",
    "x-codeSamples",
    "tags",
}


def contract(value, *, names=False):
    """Drop prose, preserving authored names and all literal contract values."""
    if isinstance(value, list):
        return [contract(item) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: (
            item
            if key in {"default", "const", "enum", "security"} and not names
            else contract(item, names=not names and key in NAME_MAPS)
        )
        for key, item in value.items()
        if names or key not in ANNOTATIONS
    }


def assert_v1_compatible(baseline, current):
    """Conservative guard: existing structures stay fixed; new operations may be added."""
    for key in ("openapi", "security", "servers", "jsonSchemaDialect"):
        assert current.get(key) == baseline.get(key), f"Global contract changed: {key}"
    for path, methods in baseline["paths"].items():
        for method, operation in methods.items():
            actual = current.get("paths", {}).get(path, {}).get(method)
            assert actual == operation, f"Existing operation changed: {method.upper()} {path}"
    for category, members in baseline.get("components", {}).items():
        for name, component in members.items():
            actual = current.get("components", {}).get(category, {}).get(name)
            assert actual == component, f"Existing component changed: {category}/{name}"


def test_existing_v1_http_contract_is_preserved(schema):
    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert_v1_compatible(baseline, contract(schema))


@pytest.mark.parametrize(
    "target,value",
    [
        (("paths", "/api/v1/health"), None),
        (("paths", "/api/v1/health", "get"), None),
        (("paths", "/api/v1/health", "get", "responses", "200"), None),
        (("paths", "/api/v1/users/me", "get", "security"), []),
        (("paths", "/api/v1/evaluations", "get", "parameters"), []),
        (("paths", "/api/v1/health", "get", "responses", "200", "content"), {}),
        (("components", "schemas", "ErrorCode", "enum"), ["INTERNAL_ERROR"]),
        (("components", "schemas", "LoginInput", "required"), ["username", "password", "extra"]),
        (("components", "schemas", "LoginInput", "properties", "username", "type"), "integer"),
        (("components", "schemas", "LoginInput", "properties", "username", "maxLength"), 1),
        (("components", "schemas", "LoginInput", "properties", "password"), None),
        (("components", "securitySchemes", "HTTPBearer", "scheme"), "basic"),
        (("openapi",), "3.0.0"),
        (("security",), [{"NewAuth": []}]),
        (("servers",), [{"url": "https://changed.invalid"}]),
    ],
)
def test_guard_rejects_existing_contract_changes(schema, target, value):
    from copy import deepcopy

    baseline = contract(schema)
    changed = deepcopy(baseline)
    parent = changed
    for key in target[:-1]:
        parent = parent[key]
    if value is None:
        del parent[target[-1]]
    else:
        parent[target[-1]] = value
    with pytest.raises(AssertionError, match="changed"):
        assert_v1_compatible(baseline, changed)


def test_guard_allows_new_operations_components_and_prose(schema):
    from copy import deepcopy

    changed = deepcopy(schema)
    changed["paths"]["/api/v1/new"] = {"get": {"responses": {"200": {"description": "OK"}}}}
    changed["paths"]["/api/v1/health"]["post"] = {"responses": {"204": {"description": "OK"}}}
    changed["components"]["schemas"]["NewModel"] = {"type": "string"}
    changed["paths"]["/api/v1/health"]["get"]["description"] = "Updated prose"
    changed["components"]["schemas"]["LoginInput"]["description"] = "Updated prose"
    assert_v1_compatible(contract(schema), contract(changed))


def test_contract_keeps_authored_field_names_and_literal_values():
    schema = {
        "description": "Prose",
        "properties": {"description": {"type": "string"}, "example": {"type": "integer"}},
        "default": {"description": "literal"},
        "enum": [{"title": "literal"}],
        "security": [{"description": []}],
    }
    assert contract(schema) == {
        "properties": {"description": {"type": "string"}, "example": {"type": "integer"}},
        "default": {"description": "literal"},
        "enum": [{"title": "literal"}],
        "security": [{"description": []}],
    }
