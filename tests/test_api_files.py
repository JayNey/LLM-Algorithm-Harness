"""HTTP integration and concurrent storage tests for private file processing."""

import asyncio
import csv
import io
import json
import secrets
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.files.config import FileSettings
from api.files.service import FileService
from api.main import create_app
from src.models import ExecutionResult

PASSWORD = "long-file-service-password!"


def auth_headers(tokens):
    return {"Authorization": "Bearer " + tokens["access_token"]}


def signup(client, username):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "email": username + "@example.org", "password": PASSWORD},
    )
    assert response.status_code == 201, response.text
    response = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def problem(pid="p1", **kwargs):
    return {
        "problem_id": pid,
        "title": "Example",
        "description": "Return the integer x from the provided input.",
        "difficulty": "easy",
        "tags": ["array"],
        "test_cases": [{"input": {"x": 1}, "expected_output": 1}],
        **kwargs,
    }


def csv_data(problems):
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(problems[0]))
    writer.writeheader()
    for item in problems:
        writer.writerow(
            {
                k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                for k, v in item.items()
            }
        )
    return out.getvalue().encode("utf-8-sig")


def upload(
    client,
    tokens,
    payload,
    filename="题库.json",
    route="/api/v1/files/upload",
    mime="application/json",
    **fields,
):
    raw = (
        payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode()
    )
    return client.post(
        route, headers=auth_headers(tokens), files={"file": (filename, raw, mime)}, data=fields
    )


def new_task(client, tokens):
    key = client.post(
        "/api/v1/api-keys",
        headers=auth_headers(tokens),
        json={"provider": "openai", "key_name": "test", "api_key": "fake-file-test-key"},
    )
    assert key.status_code == 201
    task = client.post(
        "/api/v1/evaluations",
        headers=auth_headers(tokens),
        json={
            "problem_ids": ["p1"],
            "strategy_names": ["vanilla"],
            "api_key_id": key.json()["data"]["id"],
            "model": "gpt-4o-mini",
        },
    )
    assert task.status_code == 201, task.text
    return task.json()["data"]["evaluation_id"]


@pytest.fixture(autouse=True)
def celery_submit():
    with (
        patch("src.task_manager.celery_app.send_task") as send_task,
        patch("src.task_manager.celery_app.AsyncResult") as async_result,
    ):
        send_task.side_effect = lambda *args, **kwargs: Mock(id=str(uuid.uuid4()))
        async_result.return_value.state = "PENDING"
        yield send_task


@pytest.fixture
def api(tmp_path):
    auth = AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
        AUTH_RATE_LIMIT=1000,
        AUTH_PROTECTED_RATE_LIMIT=1000,
    )
    files = FileSettings(
        _env_file=None,
        UPLOAD_DIR=tmp_path / "uploads",
        FILE_UPLOAD_MAX_BYTES=1024 * 1024,
        FILE_MAX_USER_BYTES=4 * 1024 * 1024,
        FILE_UPLOAD_RATE_LIMIT=1000,
    )
    app = create_app(auth, files)
    with TestClient(app) as client:
        alice, bob = signup(client, "alice"), signup(client, "bob")
        yield client, alice, bob, app, auth, files


def test_unique_private_upload_metadata_download_and_deletion(api):
    client, alice, bob, app, _, _ = api
    first = upload(client, alice, {"message": "中文内容"}).json()["data"]["file"]
    second = upload(client, alice, {"message": "中文内容"}).json()["data"]["file"]
    assert first["id"] != second["id"] and first["sha256"] == second["sha256"]
    assert "relative_path" not in first and "user_id" not in first
    response = client.get(f"/api/v1/files/{first['id']}/download", headers=auth_headers(alice))
    assert response.status_code == 200 and response.json()["message"] == "中文内容"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["content-disposition"].startswith("attachment;")
    assert response.headers["cache-control"] == "no-store"
    for suffix in ["", "/download"]:
        assert (
            client.get(
                f"/api/v1/files/{first['id']}{suffix}", headers=auth_headers(bob)
            ).status_code
            == 404
        )
        assert client.get(f"/api/v1/files/{first['id']}{suffix}").status_code == 401
    assert (
        client.delete(f"/api/v1/files/{first['id']}", headers=auth_headers(bob)).status_code == 404
    )
    owner = app.state.auth.store.find_user("alice")["id"]
    record = app.state.files.store.owned_file(first["id"], owner)
    path = app.state.files.path(record["relative_path"], owner)
    assert path.name.startswith(first["id"]) and path.exists()
    assert (
        client.delete(f"/api/v1/files/{first['id']}", headers=auth_headers(alice)).status_code
        == 204
    )
    assert not path.exists()
    assert (
        client.get(f"/api/v1/files/{first['id']}/download", headers=auth_headers(alice)).status_code
        == 404
    )


@pytest.mark.parametrize(
    "name", ["../a.json", "a/b.json", "a\\b.json", "C:a.json", "CON.json", "a.exe"]
)
def test_rejects_path_and_executable_filenames(api, name):
    client, alice, _, _, _, settings = api
    response = upload(client, alice, {}, filename=name)
    assert response.status_code in {400, 415}
    assert list(settings.UPLOAD_DIR.rglob("*.part")) == []
    assert list(settings.UPLOAD_DIR.rglob("*.json")) == []


@pytest.mark.parametrize(
    "suffix,payload",
    [
        ("json", b"MZ\x00program"),
        ("yaml", b"\x7fELFprogram"),
        ("csv", b"#!python,executable"),
        ("json", b'{"x":1,"x":2}'),
        ("json", b'{"x":NaN}'),
        ("json", b"{bad"),
        ("yaml", b'!!python/object/apply:os.system ["echo bad"]'),
        ("yaml", b"x: &ref [1]\ny: *ref\n"),
        ("yaml", b"x: 1\nx: 2\n"),
        ("json", b'["' + b"x\xff" + b'"]'),
        ("csv", b"a,a\n1,2\n"),
        ("csv", b"a,b\n1,2,3\n"),
    ],
)
def test_content_grammar_and_header_checks(api, suffix, payload):
    client, alice, _, _, _, settings = api
    response = upload(client, alice, payload, filename="data." + suffix, mime="text/plain")
    assert response.status_code == 400, response.text
    assert list(settings.UPLOAD_DIR.rglob("*.part")) == []


def test_rejects_wrong_media_type_and_deep_json(api):
    client, alice, _, _, _, _ = api
    assert upload(client, alice, {}, mime="application/x-msdownload").status_code == 415
    payload = ("[" * 70 + "0" + "]" * 70).encode()
    assert upload(client, alice, payload).status_code == 400


def test_file_byte_limit_after_parse_and_user_quota(api):
    client, alice, _, app, _, settings = api
    settings.FILE_UPLOAD_MAX_BYTES = 100
    response = upload(client, alice, {"x": "x" * 100})
    assert response.status_code == 413
    assert list(settings.UPLOAD_DIR.rglob("*.part")) == []
    settings.FILE_UPLOAD_MAX_BYTES = 1024
    settings.FILE_MAX_USER_BYTES = 30
    assert upload(client, alice, {"x": "x" * 10}).status_code == 201
    assert upload(client, alice, {"x": "x" * 10}).status_code == 413
    owner = app.state.auth.store.find_user("alice")["id"]
    with app.state.files.store.connection() as db:
        assert (
            db.execute(
                "SELECT COUNT(*) FROM api_file_objects WHERE user_id=?", (owner,)
            ).fetchone()[0]
            == 1
        )


def test_declared_and_chunked_body_caps_and_auth_before_parsing(api, monkeypatch):
    client, alice, _, app, _, settings = api
    settings.FILE_UPLOAD_MAX_BYTES = 10
    boundary = "test-boundary"
    prefix = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="x.json"\r\nContent-Type: application/json\r\n\r\n'
    ).encode()
    raw = prefix + b'"' + b"x" * 70000 + b'"\r\n--' + boundary.encode() + b"--\r\n"
    mime = {"Content-Type": "multipart/form-data; boundary=" + boundary}
    assert (
        client.post(
            "/api/v1/files/upload", content=raw, headers={**auth_headers(alice), **mime}
        ).status_code
        == 413
    )
    closed = []
    import starlette.formparsers as parser

    real = parser.SpooledTemporaryFile

    def spool(*args, **kwargs):
        kwargs["max_size"] = 1
        value = real(*args, **kwargs)
        closed.append(value)
        return value

    monkeypatch.setattr(parser, "SpooledTemporaryFile", spool)

    async def chunked_request():
        events = iter(
            [
                {"type": "http.request", "body": prefix, "more_body": True},
                {"type": "http.request", "body": b"x" * 33000, "more_body": True},
                {"type": "http.request", "body": b"x" * 33000, "more_body": True},
            ]
        )
        messages = []

        async def receive():
            return next(events, {"type": "http.disconnect"})

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/files/upload",
            "raw_path": b"/api/v1/files/upload",
            "query_string": b"",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in {**auth_headers(alice), **mime}.items()
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        assert [m["status"] for m in messages if m["type"] == "http.response.start"] == [413]

    asyncio.run(chunked_request())
    assert closed and all(file.closed for file in closed)
    closed.clear()
    assert client.post("/api/v1/files/upload", content=raw, headers=mime).status_code == 401
    assert closed == []


def test_multipart_shape_field_limits_and_upload_rate(api):
    client, alice, _, _, _, settings = api
    headers = auth_headers(alice)
    assert (
        client.post("/api/v1/files/upload", headers=headers, json={"file": "x"}).status_code == 415
    )
    response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files=[
            ("file", ("one.json", b"{}", "application/json")),
            ("other", ("two.json", b"{}", "application/json")),
        ],
    )
    assert response.status_code == 400
    response = client.post(
        "/api/v1/files/upload",
        headers=headers,
        files={"file": ("x.json", b"{}", "application/json")},
        data={"oversize": "x" * 66000},
    )
    assert response.status_code == 400
    settings.FILE_UPLOAD_RATE_LIMIT = 1
    response = upload(client, alice, {})
    assert response.status_code == 429 and "retry-after" in response.headers


def test_json_validation_report_append_duplicate_and_overwrite(api):
    client, alice, bob, _, _, _ = api
    response = upload(
        client, alice, [problem("a"), {"problem_id": "bad"}], route="/api/v1/problems/upload"
    )
    assert response.status_code == 200, response.text
    report = response.json()["data"]["validation"]
    assert report["total"] == 2 and report["valid"] == 1 and report["invalid"] == 1
    assert report["imported"] == 1 and report["errors"][0]["index"] == 1
    response = upload(
        client,
        alice,
        [problem("a", title="changed"), problem("b"), problem("b")],
        route="/api/v1/problems/upload",
    )
    assert response.status_code == 200
    report = response.json()["data"]["validation"]
    assert report["duplicates"] == 2 and report["imported"] == 1
    data = client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()
    assert [p["problem_id"] for p in data] == ["a", "b"] and data[0]["title"] == "Example"
    assert client.get("/api/v1/problems/export", headers=auth_headers(bob)).json() == []
    response = upload(
        client, alice, [problem("c")], route="/api/v1/problems/upload", mode="overwrite"
    )
    assert response.status_code == 200
    assert [
        p["problem_id"]
        for p in client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()
    ] == ["c"]


@pytest.mark.parametrize("payload", [[], [{}], [1], {"not": "array"}])
def test_invalid_datasets_do_not_destroy_existing_dataset(api, payload):
    client, alice, _, _, _, settings = api
    assert upload(client, alice, [problem()], route="/api/v1/problems/upload").status_code == 200
    assert (
        upload(
            client, alice, payload, route="/api/v1/problems/upload", mode="overwrite"
        ).status_code
        == 400
    )
    assert len(client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()) == 1
    assert list(settings.UPLOAD_DIR.rglob("*.part")) == []


def test_validation_cannot_be_disabled_and_mode_is_validated(api):
    client, alice, _, _, _, _ = api
    assert (
        upload(
            client, alice, [problem()], route="/api/v1/problems/upload", validate="false"
        ).status_code
        == 400
    )
    assert (
        upload(
            client, alice, [problem()], route="/api/v1/problems/upload", mode="merge-other"
        ).status_code
        == 400
    )


def test_csv_batch_import_and_safe_export(api):
    client, alice, _, _, _, _ = api
    raw = csv_data([problem("a", title="中文标题"), problem("b")])
    response = upload(
        client, alice, raw, filename="batch.csv", mime="text/csv", route="/api/v1/problems/upload"
    )
    assert response.status_code == 200, response.text
    response = client.get("/api/v1/problems/export?format=csv", headers=auth_headers(alice))
    assert response.status_code == 200 and response.content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert json.loads(rows[0]["title"]) == "中文标题" and json.loads(rows[0]["public_test_cases"])[
        0
    ]["input"] == {"x": 1}
    assert (
        client.get("/api/v1/problems/export?format=exe", headers=auth_headers(alice)).status_code
        == 400
    )
    assert (
        upload(
            client,
            alice,
            [problem("formula", title='=HYPERLINK("bad")')],
            route="/api/v1/problems/upload",
            mode="overwrite",
        ).status_code
        == 200
    )
    response = client.get("/api/v1/problems/export?format=csv", headers=auth_headers(alice))
    row = next(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert not row["title"].startswith("=")
    assert json.loads(row["title"]).startswith("=HYPERLINK")


def test_existing_upload_background_import_and_owner_progress(api):
    client, alice, bob, app, _, _ = api
    file_id = upload(client, alice, [problem()]).json()["data"]["file"]["id"]
    assert (
        client.post(
            "/api/v1/problems/import", headers=auth_headers(bob), json={"file_id": file_id}
        ).status_code
        == 404
    )
    response = client.post(
        "/api/v1/problems/import", headers=auth_headers(alice), json={"file_id": file_id}
    )
    assert response.status_code == 202, response.text
    assert response.json()["data"]["status"] == "pending"
    assert response.json()["data"]["task_id"]
    job_id = response.json()["data"]["job_id"]
    owner = app.state.auth.store.find_user("alice")["id"]
    assert client.get(f"/api/v1/imports/{job_id}", headers=auth_headers(bob)).status_code == 404
    queued = client.get(f"/api/v1/imports/{job_id}", headers=auth_headers(alice)).json()["data"]
    assert queued["status"] == "pending"
    app.state.files.process_job(job_id, owner)
    progress = client.get(f"/api/v1/imports/{job_id}", headers=auth_headers(alice)).json()["data"]
    assert (
        progress["status"] == "completed"
        and progress["processed"] == 1
        and progress["percentage"] == 100
    )
    bad_id = upload(client, alice, [{}]).json()["data"]["file"]["id"]
    response = client.post(
        "/api/v1/problems/import", headers=auth_headers(alice), json={"file_id": bad_id}
    )
    assert response.status_code == 202
    assert response.json()["data"]["task_id"]
    app.state.files.process_job(response.json()["data"]["job_id"], owner)
    progress = client.get(
        "/api/v1/imports/" + response.json()["data"]["job_id"], headers=auth_headers(alice)
    ).json()["data"]
    assert progress["status"] == "failed" and progress["result"]["status_code"] == 400


def test_concurrent_append_preserves_both_datasets_across_services(api):
    client, alice, _, app, _, settings = api
    owner = app.state.auth.store.find_user("alice")["id"]
    second = FileService(app.state.auth, settings)
    jobs = []
    for pid in ["one", "two"]:
        file_id = upload(client, alice, [problem(pid)]).json()["data"]["file"]["id"]
        jobs.append(app.state.files.store.create_job(file_id, owner, "append"))
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(service.process_job, job_id, owner)
            for service, job_id in zip([app.state.files, second], jobs)
        ]
        for future in futures:
            future.result()
    assert {p["problem_id"] for p in second.store.dataset(owner)} == {"one", "two"}


def test_running_progress_and_active_source_not_cleaned(api, monkeypatch):
    client, alice, _, app, _, _ = api
    import api.files.service as module

    owner = app.state.auth.store.find_user("alice")["id"]
    file_id = upload(client, alice, [problem(str(i)) for i in range(200)]).json()["data"]["file"][
        "id"
    ]
    job_id = app.state.files.store.create_job(file_id, owner, "append")
    original = module.validate_problem
    blocked, release = threading.Event(), threading.Event()
    count = 0

    def validate(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 101:
            blocked.set()
            assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr(module, "validate_problem", validate)
    worker = threading.Thread(target=app.state.files.process_job, args=(job_id, owner))
    worker.start()
    try:
        assert blocked.wait(5)
        progress = client.get(f"/api/v1/imports/{job_id}", headers=auth_headers(alice)).json()[
            "data"
        ]
        assert (
            progress["status"] == "running"
            and progress["processed"] == 100
            and progress["total"] == 200
        )
        with app.state.files.store.connection() as db:
            db.execute("UPDATE api_file_objects SET expires_at=1 WHERE id=?", (file_id,))
        app.state.files.cleanup()
        app.state.files.store.owned_file(file_id, owner, allow_expired=True)
        assert client.delete(
            f"/api/v1/files/{file_id}", headers=auth_headers(alice)
        ).status_code in {404, 409}
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert app.state.files.store.job(job_id, owner)["status"] == "completed"


def test_item_count_and_merged_dataset_size_limits(api):
    client, alice, _, app, _, settings = api
    settings.FILE_IMPORT_MAX_ITEMS = 1
    assert (
        upload(
            client, alice, [problem("a"), problem("b")], route="/api/v1/problems/upload"
        ).status_code
        == 413
    )
    settings.FILE_IMPORT_MAX_ITEMS = 10
    assert upload(client, alice, [problem("a")], route="/api/v1/problems/upload").status_code == 200
    settings.FILE_IMPORT_MAX_ITEMS = 1
    assert upload(client, alice, [problem("b")], route="/api/v1/problems/upload").status_code == 413
    assert len(app.state.files.store.dataset(app.state.auth.store.find_user("alice")["id"])) == 1


@pytest.mark.parametrize("kind", ["harness", "experiment"])
@pytest.mark.parametrize("suffix", ["json", "yaml", "yml"])
def test_config_validation_templates_and_no_secret_persistence(api, kind, suffix, caplog):
    client, alice, _, _, _, settings = api
    name = "vanilla" if kind == "harness" else "experiment"
    template = client.get("/api/v1/configs/templates/" + name, headers=auth_headers(alice)).json()[
        "data"
    ]
    cfg = template["config"]
    actual = "private-upload-config-key"
    if kind == "harness":
        cfg["llm_config"]["api_key"] = actual
    else:
        cfg["models"][0]["api_key"] = actual
    data = (
        yaml.safe_dump(cfg, allow_unicode=True).encode()
        if suffix != "json"
        else json.dumps(cfg).encode()
    )
    response = upload(
        client,
        alice,
        data,
        filename="config." + suffix,
        mime="text/plain",
        route="/api/v1/configs/upload",
        config_type=kind,
    )
    assert response.status_code == 201, response.text
    assert actual not in response.text and actual not in caplog.text
    file_id = response.json()["data"]["file"]["id"]
    downloaded = client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers(alice))
    assert actual.encode() not in downloaded.content and b"[REDACTED]" in downloaded.content
    for path in settings.UPLOAD_DIR.rglob("*"):
        if path.is_file():
            assert actual.encode() not in path.read_bytes()
    assert list(settings.UPLOAD_DIR.rglob("*.part")) == []


def test_invalid_config_has_field_errors_without_input_values(api):
    client, alice, _, _, _, _ = api
    actual = "private-upload-bad-key"
    response = upload(
        client,
        alice,
        {"llm_config": {"provider": "wrong", "api_key": actual}},
        route="/api/v1/configs/upload",
    )
    assert response.status_code == 400 and actual not in response.text
    errors = response.json()["detail"]["errors"]
    assert any(e["field"] == "llm_config.provider" for e in errors)
    assert client.get("/api/v1/configs/templates/../../etc").status_code != 200
    assert (
        client.get("/api/v1/configs/templates/nope", headers=auth_headers(alice)).status_code == 404
    )
    assert (
        len(client.get("/api/v1/configs/templates", headers=auth_headers(alice)).json()["data"])
        == 2
    )


def test_generic_config_bypass_and_config_specific_size_limit(api):
    client, alice, _, _, _, settings = api
    cfg = client.get("/api/v1/configs/templates/vanilla", headers=auth_headers(alice)).json()[
        "data"
    ]["config"]
    assert upload(client, alice, cfg).status_code == 400
    settings.FILE_CONFIG_MAX_BYTES = 100
    assert upload(client, alice, cfg, route="/api/v1/configs/upload").status_code == 413
    assert (
        upload(
            client,
            alice,
            b"a,b\n1,2\n",
            filename="config.csv",
            mime="text/csv",
            route="/api/v1/configs/upload",
        ).status_code
        == 400
    )


@pytest.mark.parametrize("format_name", ["json", "csv", "markdown", "html", "png", "zip"])
def test_result_download_formats_and_owner_boundaries(api, format_name):
    client, alice, bob, app, _, _ = api
    run_id = new_task(client, alice)
    owner = app.state.auth.store.find_user("alice")["id"]
    assert (
        client.get(f"/api/v1/results/{run_id}/download", headers=auth_headers(alice)).status_code
        == 404
    )
    result = ExecutionResult(
        problem_id="=bad-formula",
        strategy="vanilla",
        generated_code="print('<script>bad</script>')",
        status="success",
        metadata={"api_key": "should-be-redacted"},
    )
    app.state.files.publish_results(run_id, owner, {"vanilla": [result]})
    response = client.get(
        f"/api/v1/results/{run_id}/export?format={format_name}", headers=auth_headers(alice)
    )
    assert response.status_code == 200, (
        response.text[:200] if format_name not in {"png", "zip"} else response.status_code
    )
    assert response.headers["content-disposition"].startswith("attachment")
    if format_name == "json":
        assert response.json()["vanilla"][0]["metadata"]["api_key"] == "[REDACTED]"
    elif format_name == "csv":
        assert "'=bad-formula" in response.content.decode("utf-8-sig")
    elif format_name == "html":
        assert "<script>bad</script>" not in response.text and "&lt;script&gt;" in response.text
    elif format_name == "png":
        assert response.content.startswith(b"\x89PNG\r\n\x1a\n")
    elif format_name == "zip":
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            assert set(archive.namelist()) == {
                "results.json",
                "results.csv",
                "report.md",
                "report.html",
                "success-rate.png",
            }
            assert all(not n.startswith("/") and ".." not in n for n in archive.namelist())
            assert b"should-be-redacted" not in archive.read("results.json")
    assert (
        client.get(
            f"/api/v1/results/{run_id}/export?format={format_name}", headers=auth_headers(bob)
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/results/{run_id}/export?format={format_name}").status_code == 401


def test_run_deletion_cleans_artifacts_and_blocks_late_worker(api):
    client, alice, _, app, _, _ = api
    run_id = new_task(client, alice)
    owner = app.state.auth.store.find_user("alice")["id"]
    result = ExecutionResult(
        problem_id="p1", strategy="vanilla", generated_code="pass", status="success"
    )
    meta = app.state.files.publish_results(run_id, owner, {"vanilla": [result]})
    row = app.state.files.store.owned_file(meta["id"], owner)
    path = app.state.files.path(row["relative_path"], owner)
    assert (
        client.delete(f"/api/v1/evaluations/{run_id}", headers=auth_headers(alice)).status_code
        == 204
    )
    assert not path.exists()
    assert (
        client.get(f"/api/v1/results/{run_id}/download", headers=auth_headers(alice)).status_code
        == 404
    )
    with pytest.raises(HTTPException) as exc:
        app.state.files.publish_results(run_id, owner, {"vanilla": [result]})
    assert exc.value.status_code == 404
    with pytest.raises(HTTPException):
        app.state.files.publish_results("../unregistered", owner, {"vanilla": [result]})


def test_cleanup_retries_permission_error_and_expires_stale_jobs(api, monkeypatch):
    client, alice, _, app, _, _ = api
    owner = app.state.auth.store.find_user("alice")["id"]
    file_id = upload(client, alice, [problem()]).json()["data"]["file"]["id"]
    row = app.state.files.store.owned_file(file_id, owner)
    path = app.state.files.path(row["relative_path"], owner)
    job_id = app.state.files.store.create_job(file_id, owner, "append")
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_jobs SET updated_at=1 WHERE id=?", (job_id,))
        db.execute("UPDATE api_file_objects SET expires_at=1 WHERE id=?", (file_id,))
    real = Path.unlink

    def deny(self, *args, **kwargs):
        if self == path:
            raise PermissionError("busy file")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", deny)
    assert app.state.files.cleanup() == 0
    assert path.exists() and app.state.files.store.job(job_id, owner)["status"] == "failed"
    monkeypatch.setattr(Path, "unlink", real)
    assert app.state.files.cleanup() == 1
    assert not path.exists()


def test_periodic_cleanup_and_orphan_stage_cleanup(api):
    client, alice, _, app, _, settings = api
    owner = app.state.auth.store.find_user("alice")["id"]
    metadata = upload(client, alice, {"x": 1}).json()["data"]["file"]
    record = app.state.files.store.owned_file(metadata["id"], owner)
    path = app.state.files.path(record["relative_path"], owner)
    with app.state.files.store.connection() as db:
        db.execute("UPDATE api_file_objects SET expires_at=1 WHERE id=?", (metadata["id"],))
    # Construct the lifecycle with a short interval to exercise the real timer.
    settings.FILE_CLEANUP_INTERVAL_SECONDS = 1
    with TestClient(create_app(app.state.auth.settings, settings)) as restarted:
        # Startup and subsequent cleanup both use the same persistent metadata.
        assert not path.exists()
        file_id = upload(restarted, alice, {"x": 2}).json()["data"]["file"]["id"]
        row = restarted.app.state.files.store.owned_file(file_id, owner)
        timer_path = restarted.app.state.files.path(row["relative_path"], owner)
        with restarted.app.state.files.store.connection() as db:
            db.execute("UPDATE api_file_objects SET expires_at=1 WHERE id=?", (file_id,))
        deadline = time.monotonic() + 4
        while timer_path.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not timer_path.exists()
    stage = app.state.files._temporary(owner)
    stage.close()
    import os

    os.utime(stage.name, (1, 1))
    app.state.files.cleanup()
    assert not Path(stage.name).exists()


def test_symlink_and_integrity_tampering_do_not_leak_data(api, tmp_path):
    client, alice, _, app, _, _ = api
    owner = app.state.auth.store.find_user("alice")["id"]
    file_id = upload(client, alice, {"x": 1}).json()["data"]["file"]["id"]
    row = app.state.files.store.owned_file(file_id, owner)
    path = app.state.files.path(row["relative_path"], owner)
    path.write_bytes(b'{"x":2}')
    assert (
        client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers(alice)).status_code
        == 409
    )
    secret = tmp_path / "server-secret"
    secret.write_text("private-data", encoding="utf-8")
    path.unlink()
    try:
        path.symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("Host does not permit symbolic links")
    response = client.get(f"/api/v1/files/{file_id}/download", headers=auth_headers(alice))
    assert response.status_code == 404 and "private-data" not in response.text


def test_datasets_and_uploads_survive_service_restart(api):
    client, alice, _, app, auth, settings = api
    response = upload(client, alice, [problem()], route="/api/v1/problems/upload")
    file_id = response.json()["data"]["file_id"]
    with TestClient(create_app(auth, settings)) as restarted:
        assert (
            restarted.get("/api/v1/problems/export", headers=auth_headers(alice)).json()[0][
                "problem_id"
            ]
            == "p1"
        )
        assert (
            restarted.get(
                f"/api/v1/files/{file_id}/download", headers=auth_headers(alice)
            ).status_code
            == 200
        )


def test_early_upload_rejections_have_cors_and_private_headers(api):
    client, alice, _, _, _, settings = api
    origin = {"Origin": "http://localhost:3000"}
    response = client.post(
        "/api/v1/files/upload",
        headers=origin,
        files={"file": ("x.json", b"{}", "application/json")},
    )
    assert response.status_code == 401
    assert response.headers["access-control-allow-origin"] == origin["Origin"]
    assert response.headers["cache-control"] == "no-store"
    settings.FILE_UPLOAD_MAX_BYTES = 1
    response = client.post(
        "/api/v1/files/upload",
        headers={**origin, **auth_headers(alice)},
        files={"file": ("x.json", b"{}", "application/json")},
    )
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == origin["Origin"]


def test_transfer_and_import_capacity_and_small_import_request_limit(api):
    client, alice, _, app, _, settings = api
    locks = [
        app.state.files.transfers.acquire(blocking=False)
        for _ in range(settings.FILE_MAX_CONCURRENT_TRANSFERS)
    ]
    assert all(locks)
    try:
        assert upload(client, alice, {}).status_code == 429
        assert client.get("/api/v1/problems/export", headers=auth_headers(alice)).status_code == 429
    finally:
        for _ in locks:
            app.state.files.transfers.release()
    assert upload(client, alice, {}).status_code == 201
    settings.FILE_MAX_ACTIVE_IMPORTS = 1
    owner = app.state.auth.store.find_user("alice")["id"]
    one = upload(client, alice, [problem("one")]).json()["data"]["file"]["id"]
    two = upload(client, alice, [problem("two")]).json()["data"]["file"]["id"]
    job_id = app.state.files.store.create_job(one, owner, "append", 1)
    response = client.post(
        "/api/v1/problems/import", headers=auth_headers(alice), json={"file_id": two}
    )
    assert response.status_code == 429
    app.state.files.process_job(job_id, owner)
    assert (
        client.post(
            "/api/v1/problems/import", headers=auth_headers(alice), json={"file_id": two}
        ).status_code
        == 202
    )
    response = client.post(
        "/api/v1/problems/import", headers=auth_headers(alice), content=b"x" * 17000
    )
    assert response.status_code == 413


def test_interrupted_and_idle_upload_closes_disk_spool(api, monkeypatch):
    client, alice, _, app, _, settings = api
    import starlette.formparsers as parser

    closed = []
    real = parser.SpooledTemporaryFile

    def spool(*args, **kwargs):
        kwargs["max_size"] = 1
        file = real(*args, **kwargs)
        closed.append(file)
        return file

    monkeypatch.setattr(parser, "SpooledTemporaryFile", spool)
    settings.FILE_UPLOAD_IDLE_SECONDS = 1
    prefix = (
        b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="x.json"\r\n\r\n{}'
    )

    async def request(disconnect):
        sent_first = False
        messages = []

        async def receive():
            nonlocal sent_first
            if not sent_first:
                sent_first = True
                return {"type": "http.request", "body": prefix, "more_body": True}
            if disconnect:
                return {"type": "http.disconnect"}
            await asyncio.sleep(10)
            return {"type": "http.disconnect"}

        async def send(message):
            messages.append(message)

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": "/api/v1/files/upload",
            "raw_path": b"/api/v1/files/upload",
            "query_string": b"",
            "headers": [
                (b"authorization", auth_headers(alice)["Authorization"].encode()),
                (b"content-type", b"multipart/form-data; boundary=boundary"),
            ],
            "client": ("testclient", 5000),
            "server": ("testserver", 80),
        }
        await app(scope, receive, send)
        return [m["status"] for m in messages if m["type"] == "http.response.start"]

    assert asyncio.run(request(True)) == [400]
    assert asyncio.run(request(False)) == [408]
    assert closed and all(file.closed for file in closed)
    # Both failures release the capacity lease.
    assert upload(client, alice, {}).status_code == 201


def test_crash_rename_orphans_reclaimed_but_registered_objects_preserved(api):
    import os
    import uuid

    client, alice, _, app, _, _ = api
    owner = app.state.auth.store.find_user("alice")["id"]
    file_id = upload(client, alice, {"x": 1}).json()["data"]["file"]["id"]
    row = app.state.files.store.owned_file(file_id, owner)
    registered = app.state.files.path(row["relative_path"], owner)
    orphan = registered.with_name(str(uuid.uuid4()) + ".json")
    orphan.write_bytes(b"{}")
    arbitrary = registered.with_name("keep-me.json")
    arbitrary.write_bytes(b"{}")
    fresh = registered.with_name(str(uuid.uuid4()) + ".json")
    fresh.write_bytes(b"{}")
    for path in [registered, orphan, arbitrary]:
        os.utime(path, (1, 1))
    assert app.state.files.cleanup() == 1
    assert not orphan.exists()
    assert registered.exists() and arbitrary.exists() and fresh.exists()


def test_csv_roundtrip_preserves_judge_entry_source_optional_and_formula_strings(api):
    client, alice, _, _, _, _ = api
    original = problem(
        "=custom",
        title="=HYPERLINK('unsafe')",
        entry_point="solve(**test_input)",
        judge_config={"comparison": "exact"},
        unsupported_reason="interactive",
        source_metadata={"contest": "ABC", "rating": 1234},
        source_problem_id=None,
        manual_completion_notes=["keep metadata"],
        constraints="",
        needs_manual_completion=True,
    )
    response = upload(client, alice, [original], route="/api/v1/problems/upload")
    assert response.status_code == 200, response.text
    expected = client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()
    exported = client.get("/api/v1/problems/export?format=csv", headers=auth_headers(alice))
    response = upload(
        client,
        alice,
        exported.content,
        filename="roundtrip.csv",
        mime="text/csv",
        route="/api/v1/problems/upload",
        mode="overwrite",
    )
    assert response.status_code == 200, response.text
    actual = client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()
    assert actual == expected
    assert actual[0]["judge_config"]["comparison"] == "exact"
    assert actual[0]["entry_point"] == "solve(**test_input)"
    assert actual[0]["unsupported_reason"] == "interactive"


def test_plain_csv_judge_metadata_columns_and_unknown_problem_fields(api):
    client, alice, _, _, _, _ = api
    row = problem(
        "csv-custom",
        judge_config={"comparison": "exact"},
        source_metadata={"source": "custom"},
        manual_completion_notes=["keep"],
    )
    response = upload(
        client,
        alice,
        csv_data([row]),
        filename="custom.csv",
        mime="text/csv",
        route="/api/v1/problems/upload",
    )
    assert response.status_code == 200, response.text
    actual = client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()[0]
    assert actual["judge_config"]["comparison"] == "exact" and actual["source_metadata"] == {
        "source": "custom"
    }
    assert actual["manual_completion_notes"] == ["keep"]
    wrong = problem("typo", judge={"comparison": "exact"})
    response = upload(client, alice, [wrong], route="/api/v1/problems/upload")
    assert response.status_code == 400
    errors = response.json()["detail"]["errors"]["errors"][0]["errors"]
    assert {"field": "judge", "type": "extra_forbidden"} in errors


def test_csv_roundtrip_supports_large_valid_description_cells(api):
    client, alice, _, _, _, _ = api
    item = problem("large-csv", description="text" * 40000)
    assert upload(client, alice, [item], route="/api/v1/problems/upload").status_code == 200
    exported = client.get("/api/v1/problems/export?format=csv", headers=auth_headers(alice))
    response = upload(
        client,
        alice,
        exported.content,
        filename="large.csv",
        mime="text/csv",
        route="/api/v1/problems/upload",
        mode="overwrite",
    )
    assert response.status_code == 200, response.text
    actual = client.get("/api/v1/problems/export", headers=auth_headers(alice)).json()[0]
    assert actual["description"] == item["description"]
