"""Monitoring views against real identity, artifact, and evaluation stores."""

import io
import json
import secrets
import time

import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from sqlalchemy import update

from api.auth.config import AuthSettings
from api.auth.models import KeyCreate, RegisterInput
from api.auth.service import AuthService
from api.db.models import Evaluation
from api.files.config import FileSettings
from api.files.service import FileService
from api.models import EvaluationCreateRequest
from api.monitoring.config import MonitorSettings
from api.monitoring.service import MonitorService
from api.services import EvaluationService
from src.task_service import TaskEvent


@pytest.fixture
def monitoring(tmp_path):
    auth = AuthService(
        AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
            AUTH_PROTECTED_RATE_LIMIT=5,
            AUTH_RATE_WINDOW_SECONDS=60,
        )
    )
    owners = {}
    keys = {}
    for username in ("alice", "bob"):
        owner = auth.register(
            RegisterInput(
                username=username,
                email=f"{username}@example.org",
                password="monitor-service-password",
            )
        )["id"]
        owners[username] = owner
        keys[username] = auth.add_key(
            owner,
            KeyCreate(
                provider="openai", key_name=username, api_key=f"private-provider-key-{username}"
            ),
        )["id"]
    files = FileService(
        auth,
        FileSettings(
            _env_file=None,
            UPLOAD_DIR=tmp_path / "uploads",
            FILE_UPLOAD_MAX_BYTES=4096,
            FILE_MAX_USER_BYTES=6000,
            FILE_IMPORT_MAX_ITEMS=99,
            FILE_MAX_ACTIVE_IMPORTS=7,
            FILE_MAX_CONCURRENT_IMPORTS=2,
            FILE_MAX_CONCURRENT_TRANSFERS=3,
        ),
    )
    evaluations = EvaluationService()
    monitor = MonitorService(auth, files, evaluations, MonitorSettings(_env_file=None))
    try:
        yield monitor, owners, keys
    finally:
        monitor.close()
        evaluations.close()


def upload(files, owner, payload):
    encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return (
        files.upload(io.BytesIO(encoded), "data.json", "application/json", owner)["file"],
        encoded,
    )


def task_event(run_id, **changes):
    return TaskEvent(
        **{
            "sequence": 1,
            "run_id": run_id,
            "kind": "unit_failed",
            "state": "failed",
            "timestamp": "2026-10-11T12:00:00+00:00",
            "strategy": "vanilla",
            "problem_id": "p1",
            "completed_units": 1,
            "total_units": 2,
            "message": "failure",
            **changes,
        }
    )


def test_quotas_are_owned_and_count_actual_sql_utf8_bytes(monitoring):
    monitor, owners, _ = monitoring
    alice, bob = owners["alice"], owners["bob"]
    first, first_bytes = upload(monitor.files, alice, {"message": "中文题目"})
    second, second_bytes = upload(monitor.files, alice, {"x": 2})
    bob_file, bob_bytes = upload(monitor.files, bob, {"message": "other" * 100})
    monitor.files.store.mark_file_deleted(second["id"], alice)
    monitor.files.store.create_job(first["id"], alice, "append")
    monitor.files.store.create_job(bob_file["id"], bob, "append")
    dataset = json.dumps([{"description": "中文数据"}], ensure_ascii=False)
    with monitor.auth.store.connection() as db:
        db.execute(
            "INSERT INTO api_file_datasets VALUES (?,?,?)", (alice, dataset, int(time.time()))
        )
    monitor.auth.limit("protected:" + alice, 5)
    monitor.auth.limit("protected:" + alice, 5)
    monitor.auth.limit("protected:" + bob, 5)
    alice_quota, bob_quota = monitor.quotas(alice), monitor.quotas(bob)
    assert alice_quota["scope"] == "current_user_enforced_limits"
    assert alice_quota["storage"]["used_bytes"] == len(first_bytes) + len(second_bytes)
    assert alice_quota["storage"]["file_count"] == 2
    assert alice_quota["storage"]["includes_pending_cleanup"] is True
    assert bob_quota["storage"]["used_bytes"] == len(bob_bytes)
    assert alice_quota["dataset"]["used_bytes"] == len(dataset.encode("utf-8")) > len(dataset)
    assert bob_quota["dataset"]["used_bytes"] == 0
    assert alice_quota["dataset"]["used_items"] == 1
    assert bob_quota["dataset"]["used_items"] == 0
    assert (
        alice_quota["protected_requests"]["used"] == 2
        and bob_quota["protected_requests"]["used"] == 1
    )
    assert alice_quota["imports"]["active_for_user"] == 1
    assert alice_quota["storage"]["limit_bytes"] == 6000
    assert alice_quota["dataset"]["limit_bytes"] == 4096
    assert alice_quota["dataset"]["limit_items"] == 99
    assert alice_quota["imports"]["global_active_limit"] == 7
    assert alice_quota["imports"]["per_process_concurrency"] == 2
    assert alice_quota["transfers"]["per_process_concurrency"] == 3
    for period in ("daily_api_calls", "monthly_api_calls"):
        assert alice_quota[period] == {"status": "not_configured", "limit": None, "used": None}


def test_quota_view_matches_enforced_file_limit_and_expired_rates(monitoring):
    monitor, owners, _ = monitoring
    owner = owners["alice"]
    _, encoded = upload(monitor.files, owner, {"message": "x" * 3500})
    with pytest.raises(HTTPException) as error:
        upload(monitor.files, owner, {"message": "y" * 3500})
    assert error.value.status_code == 413
    quota = monitor.quotas(owner)
    assert quota["storage"]["used_bytes"] == len(encoded)
    assert quota["storage"]["used_bytes"] < quota["storage"]["limit_bytes"]
    monitor.auth.limit("protected:" + owner, 5)
    with monitor.auth.store.connection() as db:
        db.execute("UPDATE auth_rates SET expires_at=0")
    assert monitor.quotas(owner)["protected_requests"]["used"] == 0
    assert monitor.quotas(owner)["protected_requests"]["resets_at"] is None


def test_llm_stats_do_not_treat_verification_or_usage_hooks_as_measured_calls(monitoring):
    monitor, owners, keys = monitoring
    before = monitor.llm_stats()
    assert before["key_verification_count"] == 0 and before["recorded_usage_hooks"] == 0
    for username in ("alice", "bob"):
        owner, key_id = owners[username], keys[username]
        record = monitor.auth.store.key(key_id, owner)
        monitor.auth.store.record_verification(key_id, owner, record["ciphertext"], True)
    monitor.auth.store.record_key_usage(keys["alice"], owners["alice"])
    stats = monitor.llm_stats()
    assert (
        stats["status"] == "not_configured"
        and stats["source"] == "worker_instrumentation_pending_149"
    )
    assert stats["key_verification_count"] == 2 and stats["recorded_usage_hooks"] == 1
    assert (
        stats["total_calls"] is None
        and stats["success_rate"] is None
        and stats["avg_latency_ms"] is None
    )


def test_task_snapshot_reports_real_simulator_state_and_filter(monitoring):
    monitor, owners, keys = monitoring
    created = []
    for username in ("alice", "bob"):
        response = monitor.evaluations.create_evaluation(
            EvaluationCreateRequest(
                api_key_id=keys[username],
                problem_ids=["p1", "p2"],
                strategy_names=["vanilla"],
                model="gpt-4o-mini",
            ),
            owners[username],
        )
        created.append(response.evaluation_id)
    with monitor.evaluations._engine.begin() as connection:
        connection.execute(
            update(Evaluation)
            .where(Evaluation.id == created[0])
            .values(status="completed", completed_count=2)
        )
    snapshot = monitor.task_snapshot()
    assert (
        snapshot["source"] == "persisted_business_evaluations"
        and snapshot["production_queue_configured"] is False
    )
    assert snapshot["execution_backend"] == "in_process_simulator"
    assert snapshot["total"] == 2
    assert snapshot["counts"] == {"completed": 1, "pending": 1}
    paged = monitor.task_snapshot(limit=1, offset=1)
    assert (
        len(paged["items"]) == 1 and paged["total"] == 2 and paged["counts"] == snapshot["counts"]
    )
    completed = monitor.task_snapshot("completed")
    assert completed["total"] == 1 and completed["items"][0]["task_id"] == created[0]
    assert completed["items"][0]["completed"] == 2 and completed["items"][0]["total"] == 2
    assert completed["items"][0]["owner_id"] == owners["alice"]
    with monitor.evaluations._engine.connect() as connection:
        assert (
            connection.execute(Evaluation.__table__.select().where(Evaluation.id == created[1]))
            .mappings()
            .one()["status"]
            == "pending"
        )


def test_task_event_requires_live_owner_mapping_and_redacts_before_store(monitoring):
    monitor, owners, _ = monitoring
    alice, bob = owners["alice"], owners["bob"]
    run = "aaaaaaaa-1111-2222-3333-444444444444"
    monitor.files.store.register_run(run, alice)
    event = task_event(
        run,
        message="provider failed: private-provider-key-alice password=secret",
        problem_id="private-provider-key-alice",
    )
    monitor.record_task_event(event, alice)
    rows, total = monitor.store.query_logs(user_id=alice, run_id=run)
    assert total == 1 and rows[0]["level"] == "ERROR"
    assert rows[0]["context"]["source"] == "task_service_event"
    assert rows[0]["context"]["event_sequence"] == 1
    assert rows[0]["context"]["event_timestamp"] == event.timestamp
    payload = json.dumps(rows)
    assert "private-provider-key-alice" not in payload and "password=secret" not in payload
    with pytest.raises(HTTPException) as wrong_owner:
        monitor.record_task_event(event, bob)
    assert wrong_owner.value.status_code == 404
    with pytest.raises(HTTPException) as missing:
        monitor.record_task_event(task_event("not-a-server-mapped-run"), alice)
    assert missing.value.status_code == 404
    monitor.files.store.mark_run_deleted(run, alice)
    with pytest.raises(HTTPException) as deleted:
        monitor.record_task_event(event, alice)
    assert deleted.value.status_code == 404
    assert monitor.store.query_logs()[1] == 1


def test_known_secrets_are_owner_scoped_and_skip_unreadable_keys(monitoring):
    monitor, owners, keys = monitoring
    server_secret = monitor.auth.settings.SECRET_KEY.get_secret_value()
    encryption_secret = monitor.auth.settings.ENCRYPTION_KEY.get_secret_value()
    assert set(monitor.known_secrets()) == {server_secret, encryption_secret}
    alice = monitor.known_secrets(owners["alice"])
    assert "private-provider-key-alice" in alice and "private-provider-key-bob" not in alice
    with monitor.auth.store.connection() as db:
        db.execute(
            "UPDATE auth_keys SET ciphertext=? WHERE id=?", ("unreadable-ciphertext", keys["alice"])
        )
    assert set(monitor.known_secrets(owners["alice"])) == {server_secret, encryption_secret}


def test_short_provider_key_keeps_audit_task_ownership(monitoring):
    monitor, owners, _ = monitoring
    owner, run = owners["alice"], "aaaaaaaa-1111-2222-3333-444444444444"
    monitor.auth.add_key(owner, KeyCreate(provider="openai", key_name="short", api_key="a"))
    monitor.files.store.register_run(run, owner)
    monitor.record_task_event(task_event(run, message="a"), owner)
    rows, total = monitor.store.query_logs(user_id=owner, run_id=run)
    assert total == 1 and rows[0]["message"] == "[REDACTED]"
    assert rows[0]["run_id"] == run and rows[0]["user_id"] == owner
