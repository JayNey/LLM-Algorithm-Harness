"""Business database tests for issue #151: migrations, problem import and evaluation persistence."""

import secrets
from unittest.mock import Mock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from api.auth.config import AuthSettings
from api.db import (
    ProblemStore,
    downgrade,
    make_engine,
    make_session_factory,
    offline_upgrade_sql,
    run_migrations,
    upgrade,
)
from api.files.config import FileSettings
from api.main import create_app
from api.models import EvaluationCreateRequest
from api.services.evaluation_service import EvaluationService

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"
RESTART_REASON = "interrupted by service restart"


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _bootstrap_user(client):
    client.post(
        "/api/v1/auth/register",
        json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
    )
    tokens = client.post(
        "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
    ).json()["data"]
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    key_id = client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "test", "api_key": KEY},
    ).json()["data"]["id"]
    return headers, key_id


class TestMigrations:
    def test_roundtrip_on_empty_database(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'migrate.sqlite3'}"
        run_migrations(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert {"problems", "evaluations", "evaluation_results"} <= tables

        downgrade(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert not tables & {"problems", "evaluations", "evaluation_results"}

        run_migrations(url)
        tables = set(inspect(make_engine(url)).get_table_names())
        assert {"problems", "evaluations", "evaluation_results"} <= tables

    def test_upgrade_sql_is_portable_to_postgresql(self):
        sql = offline_upgrade_sql("postgresql://user:pass@localhost:5432/business")
        assert "CREATE TABLE problems" in sql
        assert "CREATE TABLE evaluations" in sql
        assert "CREATE TABLE evaluation_results" in sql
        assert "ON DELETE CASCADE" in sql
        assert "sqlite" not in sql.lower()

    def test_evaluations_model_column_present_after_migration(self, tmp_path):
        """evaluation-real-executor Task 1：迁移后 evaluations 表必须存在可空的 model 列。"""
        url = f"sqlite:///{tmp_path / 'model_column.sqlite3'}"
        run_migrations(url)
        columns = {c["name"]: c for c in inspect(make_engine(url)).get_columns("evaluations")}

        assert "model" in columns, f"evaluations.model 缺失，现有列：{sorted(columns)}"
        assert columns["model"]["nullable"] is True
        assert str(columns["model"]["type"]).upper().startswith("VARCHAR")

    def test_evaluations_model_column_roundtrip_downgrade_upgrade(self, tmp_path):
        """evaluation-real-executor Task 1：downgrade 到 base 再 run_migrations，model 列仍在。"""
        url = f"sqlite:///{tmp_path / 'model_column_roundtrip.sqlite3'}"
        run_migrations(url)
        downgrade(url, "base")
        # 回滚到 base 后 evaluations 表已被 drop
        assert "evaluations" not in set(inspect(make_engine(url)).get_table_names())

        run_migrations(url)
        columns = {c["name"] for c in inspect(make_engine(url)).get_columns("evaluations")}
        assert "model" in columns

    def test_legacy_evaluation_rows_survive_model_column_migration(self, tmp_path):
        """evaluation-real-executor Task 8：非空库升级 head 不破坏历史行，新 model 列为 NULL。

        ``3a568a0f1b04`` 是 model 列加入前的父 revision，此时 evaluations 还没有 model
        列——历史行只能用 raw SQL 插入（ORM 会携带不存在的列）。对应 delta spec
        database-schema「评估模型标识落库」的非空库子句。
        """
        url = f"sqlite:///{tmp_path / 'legacy_rows.sqlite3'}"
        upgrade(url, "3a568a0f1b04")

        legacy_engine = make_engine(url)
        legacy_columns = {c["name"] for c in inspect(legacy_engine).get_columns("evaluations")}
        assert "model" not in legacy_columns, f"父 revision 已有 model 列：{sorted(legacy_columns)}"

        # 一行 model 不存在（即升级后为 NULL）的历史评估
        with legacy_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO evaluations (id, user_id, status, strategy_names,"
                    " problem_ids, problem_count, spent_usd, completed_count,"
                    " failed_count, created_at, updated_at)"
                    " VALUES ('legacy-evaluation-1', 'alice', 'completed',"
                    " '[\"cot\"]', '[\"two-sum\"]', 1, 0.02, 1, 0,"
                    " '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
                )
            )
        legacy_engine.dispose()

        run_migrations(url)  # upgrade head：触发本次 change 的新迁移 evaluation_add_model_column

        check_engine = make_engine(url)
        with check_engine.connect() as conn:
            columns = {c["name"]: c for c in inspect(check_engine).get_columns("evaluations")}
            row = (
                conn.execute(
                    text(
                        "SELECT id, user_id, status, spent_usd, model FROM evaluations"
                        " WHERE id = 'legacy-evaluation-1'"
                    )
                )
                .mappings()
                .one()
            )
        check_engine.dispose()

        # 新列存在且可空（不为历史行伪造值）
        assert "model" in columns
        assert columns["model"]["nullable"] is True
        # 历史行仍在且字段未被改写
        assert row["id"] == "legacy-evaluation-1"
        assert row["user_id"] == "alice"
        assert row["status"] == "completed"
        assert row["spent_usd"] == pytest.approx(0.02)
        assert row["model"] is None


class TestProblemStore:
    @pytest.fixture
    def store(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'problems.sqlite3'}"
        run_migrations(url)
        return ProblemStore(make_session_factory(make_engine(url)))

    def test_reimport_updates_in_place_without_duplicates(self, store):
        first = {"problem_id": "two-sum", "title": "Two Sum", "tags": ["array"]}
        second = {"problem_id": "two-sum", "title": "Two Sum v2", "tags": ["array", "hash"]}

        assert store.upsert_import([first]) == 1
        assert store.upsert_import([second]) == 1

        assert store.count() == 1
        problem = store.get_by_problem_id("two-sum")
        assert problem.title == "Two Sum v2"
        assert problem.tags == ["array", "hash"]

    def test_import_json_file_is_repeatable(self, store):
        assert store.import_json_file("data/problems.json") == 12
        assert store.import_json_file("data/problems.json") == 12
        assert store.count() == 12
        assert store.get_by_problem_id("two-sum") is not None

    def test_record_without_problem_id_is_rejected(self, store):
        with pytest.raises(ValueError, match="problem_id"):
            store.upsert_import([{"title": "no id"}])


class TestEvaluationPersistence:
    def test_restart_marks_non_terminal_tasks_failed(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            created = client.post(
                "/api/v1/evaluations",
                headers=headers,
                json={
                    "api_key_id": key_id,
                    "model": "gpt-4o-mini",
                    "problem_ids": ["two-sum"],
                    "strategy_names": ["cot"],
                },
            )
            assert created.status_code == 201, created.text
            task_id = created.json()["data"]["evaluation_id"]

        # A fresh process against the same database observes the task...
        revived = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(revived) as client:
            headers, _ = _bootstrap_user(client)
            data = client.get(f"/api/v1/evaluations/{task_id}", headers=headers).json()["data"]
            assert data["status"] == "failed"
            assert data["error_message"] == RESTART_REASON

    def test_enqueued_pending_survives_restart(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1"], strategy_names=["cot"], model="gpt-4o-mini"
        )
        created = service.create_evaluation(request, "alice")
        # 启动只入队：worker 接管前评估保持 pending
        with patch("src.task_manager.celery_app.send_task", return_value=Mock()):
            started = service.start_evaluation(created.evaluation_id, "alice")
        assert started.status == "pending"

        # 已入队的 pending 评估在重启后被保留，而不是标成 failed
        revived = EvaluationService(url)
        after = revived.get_evaluation(created.evaluation_id, "alice")
        assert after.status == "pending"

    def test_rows_are_owner_scoped(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1"], strategy_names=["cot"], model="gpt-4o-mini"
        )
        created = service.create_evaluation(request, "alice")

        assert service.get_evaluation(created.evaluation_id, "alice").status == "pending"
        with pytest.raises(ValueError, match="not found"):
            service.get_evaluation(created.evaluation_id, "bob")

    def test_cancel_revokes_celery_and_marks_cancelled(self, tmp_path):
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        service = EvaluationService(url)
        request = EvaluationCreateRequest(
            api_key_id="k1", problem_ids=["p1", "p2"], strategy_names=["cot"], model="gpt-4o-mini"
        )
        created = service.create_evaluation(request, "alice")
        with patch("src.task_manager.celery_app.send_task", return_value=Mock()):
            service.start_evaluation(created.evaluation_id, "alice")

        # 取消已入队评估：revoke 对应 Celery 任务并置评估 cancelled
        with (
            patch("src.task_manager.celery_app.control.revoke") as mock_revoke,
            patch("src.task_manager.celery_app.AsyncResult") as mock_result,
        ):
            mock_result.return_value.state = "PENDING"
            cancelled = service.cancel_evaluation(created.evaluation_id, "alice")
        assert cancelled.status == "cancelled"
        mock_revoke.assert_called_once()

        after = service.get_evaluation(created.evaluation_id, "alice")
        assert after.status == "cancelled"
