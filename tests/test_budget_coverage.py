"""P5（#317）集成测试：个人预算执行与预警覆盖实验、基准与 A/B。

真实编排（HTTP 保存预算 → worker 派发单元 → 预算暂停 → 调整预算后恢复），
外部模型与通知渠道使用可控替身：LLM 客户端替换为确定实现，预警投递走 log
渠道（零网络成功）或被替换为必炸实现以验证失败隔离。
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.config import settings
from api.db.models import AlertEvent, AsyncTask, BenchmarkRun
from api.files.config import FileSettings
from api.main import create_app
from src.experiment import ExperimentRunner

PASSWORD = "a-long-test-password-!"
KEY = "sk-private-unique-test-value"


def auth_config(tmp_path):
    import secrets

    from cryptography.fernet import Fernet

    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _signup(client, name="alice"):
    register = client.post(
        "/api/v1/auth/register",
        json={"username": name, "email": f"{name}@example.org", "password": PASSWORD},
    )
    assert register.status_code == 201, register.text
    login = client.post("/api/v1/auth/login", json={"username": name, "password": PASSWORD})
    assert login.status_code == 200, login.text
    token = login.json()["data"]["access_token"]
    return {"Authorization": "Bearer " + token}


def _add_key(client, headers):
    return client.post(
        "/api/v1/api-keys",
        headers=headers,
        json={"provider": "openai", "key_name": "budget-key", "api_key": KEY},
    ).json()["data"]["id"]


@pytest.fixture
def api(tmp_path):
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
    )
    with TestClient(app) as client:
        headers = _signup(client)
        key_id = _add_key(client, headers)
        yield client, headers, key_id, app


def _fake_llm(monkeypatch):
    from types import SimpleNamespace

    def create(**_kwargs):
        return SimpleNamespace(
            model="priced/model",
            usage=SimpleNamespace(prompt_tokens=100, completion_tokens=50, total_tokens=150),
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="```python\ndef solution(x): return x + 1\n```"
                    ),
                    finish_reason="stop",
                )
            ],
        )

    monkeypatch.setattr(
        "src.llm_client.LLMClient._initialize_client",
        lambda _: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
            base_url="https://provider.invalid/v1",
        ),
    )


def _write_dataset(tmp_path, problem_id="budget-p1"):
    (tmp_path / "problems.json").write_text(
        json.dumps(
            [
                {
                    "problem_id": problem_id,
                    "title": problem_id,
                    "description": "Return the constant integer one.",
                    "difficulty": "easy",
                    "test_cases": [{"input": {"x": 1}, "expected_output": 2}],
                }
            ]
        ),
        encoding="utf-8",
    )


def _setup_pricing_and_llm(client, headers, monkeypatch):
    _fake_llm(monkeypatch)
    price = client.post(
        "/api/v1/pricing/priced%2Fmodel",
        headers=headers,
        json={"prompt_per_1k": 1, "completion_per_1k": 4},
    )
    assert price.status_code == 201, price.text


def _runner_factory(runner_cls):
    """Host 沙箱 + 关闭缓存的真 runner 工厂（与 test_api_cost 模式一致）。"""
    from src.models import SandboxConfig

    def factory(config):
        config.sandbox_config = SandboxConfig(backend="host")
        if hasattr(config, "models"):
            config.models = [
                m.model_copy(update={"cache": m.cache.model_copy(update={"enabled": False})})
                for m in config.models
            ]
        if hasattr(config, "model"):
            config.model = config.model.model_copy(
                update={"cache": config.model.cache.model_copy(update={"enabled": False})}
            )
        return runner_cls(config)

    return factory


def _alert_events(app, owner_id, rule_id=None):
    with app.state.experiments._session() as session:
        query = session.query(AlertEvent).filter(AlertEvent.user_id == owner_id)
        if rule_id is not None:
            query = query.filter(AlertEvent.rule_id == rule_id)
        return query.all()


class _RaisingSender:
    @staticmethod
    def deliver(*_a, **_k):
        raise RuntimeError("smtp down")


class _BudgetBenchmarkExecutor:
    """Honors should_pause at unit boundaries, mirroring the real executor."""

    def __init__(self, suite, config):
        self.suite = suite
        self.config = config
        self.paused = False
        self.units = 0

    def execute(self):
        for _ in range(3):
            if getattr(self, "should_pause", None) and self.should_pause():
                self.paused = True
                return None
            self.units += 1
        return {"summary": {"accuracy": 1.0, "cost_usd": 0.0}, "accuracy": 1.0, "cost_usd": 0.0}


def test_experiment_budget_pauses_records_alert_once_and_resumes(api, monkeypatch, tmp_path):
    from src.experiment import ExperimentRunner
    from src.tasks.experiment import run_experiment_task

    client, headers, key_id, app = api
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    _write_dataset(tmp_path)
    _setup_pricing_and_llm(client, headers, monkeypatch)

    budget = client.post(
        "/api/v1/budgets", headers=headers, json={"global_cap_usd": 0.02, "action": "pause"}
    )
    assert budget.status_code == 201, budget.text
    rule = client.post(
        "/api/v1/alerts",
        headers=headers,
        json={"name": "half", "threshold_pct": 50, "channel": "log", "target": ""},
    )
    assert rule.status_code == 201, rule.text
    rule_id = rule.json()["data"]["id"]

    created = client.post(
        "/api/v1/experiments",
        headers=headers,
        json={
            "dataset_path": "problems.json",
            "api_key_id": key_id,
            "models": [{"model": "priced/model"}],
            "strategies": [{"name": "vanilla"}],
            "repeats": 2,
        },
    )
    assert created.status_code == 201, created.text
    job_id = created.json()["data"]["id"]
    with patch("src.task_manager.celery_app.send_task"):
        started = client.post(f"/api/v1/experiments/{job_id}/run", headers=headers)
    assert started.status_code == 202, started.text
    task_id = started.json()["data"]["task_id"]

    monkeypatch.setattr(run_experiment_task, "update_state", lambda **_: None)
    monkeypatch.setattr("src.tasks.experiment.get_db_session", app.state.experiments._session)
    monkeypatch.setattr("src.tasks.experiment.execute_experiment", app.state.experiments._execute)
    monkeypatch.setattr("src.experiment.generate_comparison_report", lambda _: None)
    monkeypatch.setattr("src.experiment.generate_html_panel", lambda _: None)
    app.state.experiments._runner_factory = _runner_factory(ExperimentRunner)

    owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id

    def experiment_status():
        return client.get(f"/api/v1/experiments/{job_id}", headers=headers).json()["data"]["status"]

    # 预算暂停：worker 在派发边界自行暂停，无需人工干预。
    first = run_experiment_task(job_id, owner)
    assert first["status"] == "paused"
    assert experiment_status() == "paused"

    # 预警按规则触发一次（log 渠道成功落历史），跨恢复不重复。
    from api.services.cost_service import CostService as _CS

    with app.state.experiments._session() as session:
        print("DBG budget:", _CS.execution_budget(session, owner))
    print("DBG events:", _alert_events(app, owner), "| rules:", end=" ")
    with app.state.experiments._session() as session:
        from api.db.models import AlertRule as _R

        print(
            [
                (r.id[:8], r.threshold_pct, r.channel, r.enabled, r.user_id == owner)
                for r in session.query(_R).all()
            ]
        )
    events = _alert_events(app, owner, rule_id)
    assert len(events) == 1, events
    assert events[0].channel == "log"

    # 通知失败不得破坏任务状态：投递必炸时恢复仍走到暂停（而非 failed）。
    monkeypatch.setattr(
        "api.services.cost_alert_service.CostAlertSender",
        lambda *_a, **_k: _RaisingSender(),
    )
    with patch("src.task_manager.celery_app.send_task"):
        resumed = client.post(f"/api/v1/tasks/{task_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    _result = run_experiment_task(job_id, owner)
    if _result["status"] != "paused":
        with app.state.experiments._session() as session:
            from api.db.models import AsyncTask as _T

            t = session.get(_T, task_id)
            print("EXP-DEBUG error:", t.error_message if t else None)
    assert _result["status"] == "paused"
    assert experiment_status() == "paused"

    # 调整预算后恢复原任务：已完成单元与费用不重复累计，任务完成。
    assert (
        client.patch("/api/v1/budgets", headers=headers, json={"global_cap_usd": 10}).status_code
        == 200
    )
    with patch("src.task_manager.celery_app.send_task"):
        resumed = client.post(f"/api/v1/tasks/{task_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert run_experiment_task(job_id, owner)["status"] == "completed"
    assert experiment_status() == "completed"

    summary = client.get("/api/v1/costs/summary", headers=headers).json()["data"]
    assert summary["total_cost_usd"] > 0
    usage = client.get("/api/v1/budgets/usage", headers=headers).json()["data"]
    assert usage["global_budget"]["used_usd"] == summary["total_cost_usd"]
    with app.state.experiments._session() as session:
        task = session.get(AsyncTask, task_id)
        assert task is not None and task.status == "completed"
    assert len(_alert_events(app, owner, rule_id)) == 1


def test_ab_budget_downgrade_action_pauses_then_completes(api, monkeypatch, tmp_path):
    from src.ab_testing import ABTestRunner
    from src.tasks.ab_test import run_ab_test_task

    client, headers, key_id, app = api
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
    _write_dataset(tmp_path)
    _setup_pricing_and_llm(client, headers, monkeypatch)

    # downgrade 对 A/B 无保语义降级：显式按暂停处理（语义约定见 budget_guard）。
    budget = client.post(
        "/api/v1/budgets", headers=headers, json={"global_cap_usd": 0.02, "action": "downgrade"}
    )
    assert budget.status_code == 201, budget.text

    created = client.post(
        "/api/v1/ab-tests",
        headers=headers,
        json={
            "dataset_path": "problems.json",
            "api_key_id": key_id,
            "model": {"model": "priced/model"},
            "strategy": {"name": "vanilla"},
            "prompt_variants": [{"id": "a"}, {"id": "b"}],
        },
    )
    assert created.status_code == 201, created.text
    test_id = created.json()["data"]["id"]
    with patch("src.task_manager.celery_app.send_task"):
        started = client.post(f"/api/v1/ab-tests/{test_id}/run", headers=headers)
    assert started.status_code == 202, started.text
    task_id = started.json()["data"].get("task_id")
    if task_id is None:
        with app.state.ab_tests._session() as session:
            task_id = session.query(AsyncTask).filter(AsyncTask.entity_id == test_id).one().id

    monkeypatch.setattr(run_ab_test_task, "update_state", lambda **_: None)
    monkeypatch.setattr(
        "api.services.ab_test_service.ABTestService", lambda **_: app.state.ab_tests
    )
    app.state.ab_tests._runner_factory = _runner_factory(ABTestRunner)

    owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id

    _orig_finish = app.state.ab_tests._finish

    def _finish_spy(task_id, status, **kw):
        if status == "failed":
            print("AB-FAIL:", kw.get("error_message"))
        return _orig_finish(task_id, status, **kw)

    app.state.ab_tests._finish = _finish_spy
    _result = run_ab_test_task(test_id, owner)
    if _result["status"] != "paused":
        with app.state.ab_tests._session() as session:
            from api.db.models import AsyncTask as _T

            t = session.get(_T, task_id)
            rows = [(r.id[:8], r.task_type, r.status) for r in session.query(_T).all()]
            print(
                "AB-DEBUG task_id:",
                task_id[:8],
                "rows:",
                rows,
                "err:",
                t.error_message if t else None,
            )
    assert _result["status"] == "paused"

    assert (
        client.patch("/api/v1/budgets", headers=headers, json={"global_cap_usd": 10}).status_code
        == 200
    )
    with patch("src.task_manager.celery_app.send_task"):
        resumed = client.post(f"/api/v1/tasks/{task_id}/resume", headers=headers)
    assert resumed.status_code == 200, resumed.text
    assert run_ab_test_task(test_id, owner)["status"] == "completed"
    detail = client.get(f"/api/v1/ab-tests/{test_id}", headers=headers).json()["data"]
    assert detail["status"] == "completed"


def test_benchmark_budget_pauses_on_prior_spend_and_resumes(tmp_path, monkeypatch):
    from src.tasks.benchmark import run_benchmark_task
    from src.tasks.experiment import run_experiment_task

    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        benchmark_executor_factory=_BudgetBenchmarkExecutor,
    )
    with TestClient(app) as client:
        headers = _signup(client)
        key_id = _add_key(client, headers)
        monkeypatch.setattr("src.tasks.benchmark.get_db_session", app.state.benchmarks._session)
        monkeypatch.setattr(
            "src.tasks.benchmark.execute_benchmark",
            lambda run_id, user_id: app.state.benchmarks._execute(run_id, user_id),
        )

        # 先用一次实验制造已入账花费（预算上限放大让它完整跑完）。
        _setup_pricing_and_llm(client, headers, monkeypatch)
        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(settings, "DATA_ROOT", str(tmp_path))
        _write_dataset(tmp_path)
        assert (
            client.post(
                "/api/v1/budgets", headers=headers, json={"global_cap_usd": 100}
            ).status_code
            == 201
        )
        created = client.post(
            "/api/v1/experiments",
            headers=headers,
            json={
                "dataset_path": "problems.json",
                "api_key_id": key_id,
                "models": [{"model": "priced/model"}],
                "strategies": [{"name": "vanilla"}],
                "repeats": 1,
            },
        )
        assert created.status_code == 201, created.text
        job_id = created.json()["data"]["id"]
        with patch("src.task_manager.celery_app.send_task"):
            started = client.post(f"/api/v1/experiments/{job_id}/run", headers=headers)
        assert started.status_code == 202, started.text
        experiment_task_id = started.json()["data"]["task_id"]

        monkeypatch.setattr(run_experiment_task, "update_state", lambda **_: None)
        monkeypatch.setattr("src.tasks.experiment.get_db_session", app.state.experiments._session)
        monkeypatch.setattr(
            "src.tasks.experiment.execute_experiment", app.state.experiments._execute
        )
        monkeypatch.setattr("src.experiment.generate_comparison_report", lambda _: None)
        monkeypatch.setattr("src.experiment.generate_html_panel", lambda _: None)
        app.state.experiments._runner_factory = _runner_factory(ExperimentRunner)
        owner = app.state.auth.authenticate(headers["Authorization"].split()[1]).user_id
        assert run_experiment_task(job_id, owner)["status"] == "completed"
        summary = client.get("/api/v1/costs/summary", headers=headers).json()["data"]
        prior_spend = summary["total_cost_usd"]
        assert prior_spend > 0

        # 把预算压到已有花费之下：基准在第一个派发边界即暂停。
        assert (
            client.patch(
                "/api/v1/budgets", headers=headers, json={"global_cap_usd": prior_spend / 10}
            ).status_code
            == 200
        )
        suite = client.post(
            "/api/v1/benchmarks/suites",
            headers=headers,
            json={"name": "budget-suite", "problems": ["budget-p1"], "frozen": False},
        )
        assert suite.status_code == 201, suite.text
        suite_id = suite.json()["data"]["id"]
        with patch("src.task_manager.celery_app.send_task"):
            run = client.post(
                f"/api/v1/benchmarks/suites/{suite_id}/run",
                headers=headers,
                json={
                    "api_key_id": key_id,
                    "dataset_path": "problems.json",
                    "model": "priced/model",
                },
            )
        assert run.status_code == 202, run.text
        run_id = run.json()["data"]["id"]
        run_task_id = run.json()["data"]["task_id"]

        monkeypatch.setattr(run_benchmark_task, "update_state", lambda **_: None)
        assert run_benchmark_task(run_id, owner)["status"] == "paused"
        with app.state.benchmarks._session() as session:
            row = session.get(BenchmarkRun, run_id)
            assert row is not None and row.status == "paused"
            task = session.get(AsyncTask, run_task_id)
            assert task is not None and task.status == "paused"

        # 调整预算后恢复，跑完三个单元。
        assert (
            client.patch(
                "/api/v1/budgets", headers=headers, json={"global_cap_usd": 100}
            ).status_code
            == 200
        )
        with patch("src.task_manager.celery_app.send_task"):
            resumed = client.post(f"/api/v1/tasks/{run_task_id}/resume", headers=headers)
        assert resumed.status_code == 200, resumed.text
        assert run_benchmark_task(run_id, owner)["status"] == "completed"
        detail = client.get(f"/api/v1/benchmarks/runs/{run_id}", headers=headers).json()["data"]
        assert detail["status"] == "completed"
