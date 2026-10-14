"""评估 API 层正确性回归测试（verify C-1 + I-4）。

语言：zh-CN 注释。对应 Comet verify 阶段整 change 集成审查发现的两项
范围内修复：多策略进度百分比溢出（C-1 CRITICAL）与重复输入语义（I-4）。
"""

import secrets
from datetime import datetime, timezone

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.auth.config import AuthSettings
from api.db.models import Evaluation
from api.files.config import FileSettings
from api.main import create_app

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"


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


def _complete_units(app, evaluation_id, completed_count):
    """把评估标记为已完成并把 completed_count 设为给定的单元数。

    模拟真实 worker 完成后落库的状态：completed_count 为单元数（策略 × 题目），
    而 problem_count 仍为题目数——这正是 C-1 溢出的触发条件。
    """
    service = app.state.evaluations
    with Session(service.engine) as session, session.begin():
        row = session.get(Evaluation, evaluation_id)
        row.status = "completed"
        row.completed_count = completed_count
        row.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


class TestProgressPercentageOverflow:
    """C-1：多策略评估全完成后百分比不应溢出导致 500/400。"""

    def _create_multi_strategy(self, client, headers, key_id):
        resp = client.post(
            "/api/v1/evaluations",
            headers=headers,
            json={
                "api_key_id": key_id,
                "model": "gpt-4o-mini",
                "problem_ids": ["p1", "p2"],
                "strategy_names": ["vanilla", "cot"],
            },
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["data"]["evaluation_id"]

    def test_list_evaluations_returns_ok_when_all_units_complete(self, tmp_path):
        """2 策略 × 2 题目全完成（completed_count=4, problem_count=2）时列表须 200 且百分比<=100。"""
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            evaluation_id = self._create_multi_strategy(client, headers, key_id)
            _complete_units(app, evaluation_id, completed_count=4)

            listing = client.get("/api/v1/evaluations", headers=headers)
            assert listing.status_code == 200, listing.text
            items = listing.json()["data"]["items"]
            item = next(i for i in items if i["evaluation_id"] == evaluation_id)
            assert item["progress"]["percentage"] == pytest.approx(100.0)

    def test_get_evaluation_returns_ok_when_all_units_complete(self, tmp_path):
        """同一评估的详情端点在全部单元完成时应返回 200 且百分比落在 [0, 100]。"""
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            evaluation_id = self._create_multi_strategy(client, headers, key_id)
            _complete_units(app, evaluation_id, completed_count=4)

            detail = client.get(f"/api/v1/evaluations/{evaluation_id}", headers=headers)
            assert detail.status_code == 200, detail.text
            percentage = detail.json()["data"]["progress"]["percentage"]
            assert percentage == pytest.approx(100.0)


class TestDuplicateInputRejected:
    """I-4：重复的 strategy_names / problem_ids 必须在创建入口被拒。

    注：本项目的全局 RequestValidationError 处理器（api/middleware/errors.py）
    将所有请求体校验失败统一映射为 HTTP 400（而非 FastAPI 默认的 422），
    与 test_api_auth.py 对校验失败断言 400 的既有约定一致，因此这里断言 400。
    """

    def _post(self, client, headers, key_id, strategy_names, problem_ids):
        return client.post(
            "/api/v1/evaluations",
            headers=headers,
            json={
                "api_key_id": key_id,
                "model": "gpt-4o-mini",
                "problem_ids": problem_ids,
                "strategy_names": strategy_names,
            },
        )

    def test_duplicate_strategy_names_is_rejected(self, tmp_path):
        """strategy_names 含重复项时创建应被拒（400），避免幂等键重复导致的脏聚合。"""
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            resp = self._post(client, headers, key_id, ["vanilla", "vanilla"], ["p1", "p2"])
            assert resp.status_code == 400, resp.text
            assert "strategy_names" in resp.text

    def test_duplicate_problem_ids_is_rejected(self, tmp_path):
        """problem_ids 含重复项时创建应被拒（400）。"""
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            resp = self._post(client, headers, key_id, ["vanilla", "cot"], ["p1", "p1"])
            assert resp.status_code == 400, resp.text
            assert "problem_ids" in resp.text

    def test_legal_request_without_duplicates_still_201(self, tmp_path):
        """无重复的合法请求不受影响，仍返回 201（防回归）。"""
        url = f"sqlite:///{tmp_path / 'business.sqlite3'}"
        app = create_app(auth_config(tmp_path), FileSettings(), database_url=url)
        with TestClient(app) as client:
            headers, key_id = _bootstrap_user(client)
            resp = self._post(client, headers, key_id, ["vanilla", "cot"], ["p1", "p2"])
            assert resp.status_code == 201, resp.text
