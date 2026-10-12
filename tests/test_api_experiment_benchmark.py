"""API tests for experiments, benchmarks, A/B tests and analysis (issue #156)."""

import json
import secrets
import threading
import time
from pathlib import Path

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from api.auth.config import AuthSettings
from api.files.config import FileSettings
from api.main import create_app

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


class FakeExperimentRunner:
    """Writes a minimal experiment artifact tree instead of calling LLMs."""

    def __init__(self, config):
        self.config = config

    def run(self):
        out = Path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        payload = {
            "experiment_id": out.name,
            "name": self.config.name,
            "created_at": "2026-10-12T00:00:00",
            "finished_at": "2026-10-12T00:01:00",
            "models": [{"model": model.model} for model in self.config.models],
            "strategies": [
                s if isinstance(s, dict) else s.model_dump() for s in self.config.strategies
            ],
            "combinations": [],
        }
        (out / "experiment.json").write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return out


class FakeBenchmarkExecutor:
    """Returns a fixed summary instead of running the harness."""

    accuracy_values = iter([0.5, 0.75])
    last_config = None

    def __init__(self, suite, config):
        self.suite = suite
        self.config = config
        type(self).last_config = config

    def execute(self):
        try:
            accuracy = next(self.accuracy_values)
        except StopIteration:
            accuracy = 0.75
        return {
            "summary": {"accuracy": accuracy, "cost_usd": 0.05},
            "accuracy": accuracy,
            "cost_usd": 0.05,
        }


class FailingExperimentRunner:
    """Simulates a runner crash after the experiment is marked running."""

    def __init__(self, config):
        self.config = config

    def run(self):
        raise RuntimeError("provider exploded")


class BlockingExperimentRunner:
    """Keeps the experiment running until the test releases the gate."""

    def __init__(self, config):
        self.config = config

    def run(self):
        BlockingExperimentRunner.gate.wait(timeout=10)
        out = Path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "experiment.json").write_text("{}", encoding="utf-8")
        return out


class FakeABTestRunner:
    """Writes a minimal A/B report instead of calling LLMs."""

    def __init__(self, config):
        self.config = config

    def run(self):
        out = Path(self.config.output_dir)
        out.mkdir(parents=True, exist_ok=True)
        report = {
            "variants": [variant.id for variant in self.config.prompt_variants],
            "significance": {"p_value": 0.5, "significant": False},
        }
        (out / "ab_test.json").write_text(json.dumps(report), encoding="utf-8")
        return out


@pytest.fixture
def api(tmp_path):
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        experiment_runner_factory=FakeExperimentRunner,
        benchmark_executor_factory=FakeBenchmarkExecutor,
        ab_test_runner_factory=FakeABTestRunner,
    )
    with TestClient(app) as client:
        register = client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
        )
        assert register.status_code == 201, register.text
        tokens = client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
        ).json()["data"]
        headers = {"Authorization": "Bearer " + tokens["access_token"]}
        key_id = client.post(
            "/api/v1/api-keys",
            headers=headers,
            json={"provider": "openai", "key_name": "test", "api_key": KEY},
        ).json()["data"]["id"]
        yield client, headers, key_id, app


def _wait_status(client_get, target, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        data = client_get()
        if data["status"] in target:
            return data
        time.sleep(0.05)
    pytest.fail(f"did not reach {target}: {data['status']}")


def _experiment_payload(key_id):
    return {
        "name": "api-exp",
        "dataset_path": "problems.json",
        "models": [{"model": "gpt-test"}],
        "strategies": [{"name": "vanilla"}],
        "repeats": 1,
        "api_key_id": key_id,
    }


class TestExperiments:
    def test_full_lifecycle(self, api):
        client, headers, key_id, _ = api
        created = client.post(
            "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
        )
        assert created.status_code == 201, created.text
        experiment_id = created.json()["data"]["id"]
        assert created.json()["data"]["status"] == "pending"
        assert KEY not in created.text  # the raw secret never reaches responses

        started = client.post(f"/api/v1/experiments/{experiment_id}/run", headers=headers)
        assert started.status_code == 202, started.text

        data = _wait_status(
            lambda: client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                "data"
            ],
            {"completed"},
        )
        results = client.get(f"/api/v1/experiments/{experiment_id}/results", headers=headers)
        assert results.status_code == 200
        assert results.json()["data"]["name"] == "api-exp"
        comparison = client.get(f"/api/v1/experiments/{experiment_id}/comparison", headers=headers)
        assert comparison.status_code == 200
        panel = client.get(f"/api/v1/experiments/{experiment_id}/panel", headers=headers)
        assert panel.status_code == 200

        deleted = client.delete(f"/api/v1/experiments/{experiment_id}", headers=headers)
        assert deleted.status_code == 204

    def test_rejects_foreign_api_key(self, api):
        client, headers, _, _ = api
        other = client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.org", "password": PASSWORD},
        )
        assert other.status_code in (201, 409)
        bob_tokens = client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": PASSWORD}
        ).json()["data"]
        bob_key = client.post(
            "/api/v1/api-keys",
            headers={"Authorization": "Bearer " + bob_tokens["access_token"]},
            json={"provider": "openai", "key_name": "bob", "api_key": KEY},
        ).json()["data"]["id"]

        payload = _experiment_payload(bob_key)
        response = client.post("/api/v1/experiments", headers=headers, json=payload)
        assert response.status_code == 404

    def test_rejects_dataset_path_traversal(self, api):
        client, headers, key_id, _ = api
        payload = _experiment_payload(key_id)
        payload["dataset_path"] = "../secrets.json"
        response = client.post("/api/v1/experiments", headers=headers, json=payload)
        assert response.status_code == 400

    def test_delete_completed_experiment_succeeds(self, api):
        client, headers, key_id, _ = api
        experiment_id = client.post(
            "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
        ).json()["data"]["id"]
        client.post(f"/api/v1/experiments/{experiment_id}/run", headers=headers)
        _wait_status(
            lambda: client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                "data"
            ],
            {"completed"},
        )
        assert (
            client.delete(f"/api/v1/experiments/{experiment_id}", headers=headers).status_code
            == 204
        )

    def test_restart_marks_pending_experiment_failed(self, tmp_path):
        app = create_app(
            auth_config(tmp_path),
            FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
            experiment_runner_factory=FakeExperimentRunner,
        )
        auth_config_data = auth_config(tmp_path)
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
            )
            assert register.status_code == 201
            tokens = client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).json()["data"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            key_id = client.post(
                "/api/v1/api-keys",
                headers=headers,
                json={"provider": "openai", "key_name": "t", "api_key": KEY},
            ).json()["data"]["id"]
            experiment_id = client.post(
                "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
            ).json()["data"]["id"]

        revived = create_app(
            auth_config_data,
            FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
            experiment_runner_factory=FakeExperimentRunner,
        )
        with TestClient(revived) as client:
            tokens = client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).json()["data"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            data = client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                "data"
            ]
            assert data["status"] == "failed"
            assert data["error_message"] == RESTART_REASON

    def test_runner_failure_marks_experiment_failed(self, tmp_path):
        app = create_app(
            auth_config(tmp_path),
            FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
            experiment_runner_factory=FailingExperimentRunner,
        )
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
            )
            assert register.status_code == 201
            tokens = client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).json()["data"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            key_id = client.post(
                "/api/v1/api-keys",
                headers=headers,
                json={"provider": "openai", "key_name": "t", "api_key": KEY},
            ).json()["data"]["id"]
            experiment_id = client.post(
                "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
            ).json()["data"]["id"]
            assert (
                client.post(f"/api/v1/experiments/{experiment_id}/run", headers=headers).status_code
                == 202
            )
            data = _wait_status(
                lambda: client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                    "data"
                ],
                {"failed"},
            )
            assert data["error_message"] == "provider exploded"

    def test_cannot_delete_running_experiment(self, tmp_path):
        BlockingExperimentRunner.gate = threading.Event()
        app = create_app(
            auth_config(tmp_path),
            FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
            experiment_runner_factory=BlockingExperimentRunner,
        )
        with TestClient(app) as client:
            register = client.post(
                "/api/v1/auth/register",
                json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
            )
            assert register.status_code == 201
            tokens = client.post(
                "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
            ).json()["data"]
            headers = {"Authorization": "Bearer " + tokens["access_token"]}
            key_id = client.post(
                "/api/v1/api-keys",
                headers=headers,
                json={"provider": "openai", "key_name": "t", "api_key": KEY},
            ).json()["data"]["id"]
            experiment_id = client.post(
                "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
            ).json()["data"]["id"]
            client.post(f"/api/v1/experiments/{experiment_id}/run", headers=headers)
            _wait_status(
                lambda: client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                    "data"
                ],
                {"running"},
            )

            deleted = client.delete(f"/api/v1/experiments/{experiment_id}", headers=headers)
            assert deleted.status_code == 400
            assert "running" in deleted.json()["detail"]

            BlockingExperimentRunner.gate.set()
            _wait_status(
                lambda: client.get(f"/api/v1/experiments/{experiment_id}", headers=headers).json()[
                    "data"
                ],
                {"completed"},
            )

    def test_results_rejected_before_completion(self, api):
        client, headers, key_id, _ = api
        experiment_id = client.post(
            "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
        ).json()["data"]["id"]
        for path in ("results", "comparison", "panel"):
            response = client.get(f"/api/v1/experiments/{experiment_id}/{path}", headers=headers)
            assert response.status_code == 400

    def test_cross_user_access_is_404(self, api):
        client, headers, key_id, _ = api
        experiment_id = client.post(
            "/api/v1/experiments", headers=headers, json=_experiment_payload(key_id)
        ).json()["data"]["id"]

        client.post(
            "/api/v1/auth/register",
            json={"username": "carol", "email": "carol@example.org", "password": PASSWORD},
        )
        carol = client.post(
            "/api/v1/auth/login", json={"username": "carol", "password": PASSWORD}
        ).json()["data"]
        carol_headers = {"Authorization": "Bearer " + carol["access_token"]}

        assert (
            client.get(f"/api/v1/experiments/{experiment_id}", headers=carol_headers).status_code
            == 404
        )


class TestBenchmarks:
    def _suite_payload(self):
        return {
            "name": "suite-api-v1",
            "problems": ["two-sum", "reverse"],
            "description": "api suite",
            "frozen": False,
        }

    def test_suite_crud_and_freeze(self, api):
        client, headers, _, _ = api
        created = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        )
        assert created.status_code == 201, created.text
        suite_id = created.json()["data"]["id"]

        updated = client.patch(
            f"/api/v1/benchmarks/suites/{suite_id}",
            headers=headers,
            json={"problems": ["two-sum"]},
        )
        assert updated.status_code == 200
        assert updated.json()["data"]["problems"] == ["two-sum"]

        frozen = client.patch(
            f"/api/v1/benchmarks/suites/{suite_id}", headers=headers, json={"frozen": True}
        )
        assert frozen.status_code == 200
        assert frozen.json()["data"]["frozen"] is True

        rejected = client.patch(
            f"/api/v1/benchmarks/suites/{suite_id}",
            headers=headers,
            json={"problems": ["x"]},
        )
        assert rejected.status_code == 400

        listing = client.get("/api/v1/benchmarks/suites", headers=headers)
        assert listing.status_code == 200
        assert listing.json()["data"]["total"] == 1

    def test_run_results_and_learning_curve(self, api):
        client, headers, key_id, _ = api
        suite_id = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        ).json()["data"]["id"]

        run_payload = {
            "api_key_id": key_id,
            "dataset_path": "problems.json",
            "model": "gpt-test",
            "strategies": [{"name": "vanilla"}],
        }
        for _ in range(2):
            started = client.post(
                f"/api/v1/benchmarks/suites/{suite_id}/run", headers=headers, json=run_payload
            )
            assert started.status_code == 202, started.text
            run_id = started.json()["data"]["id"]
            data = _wait_status(
                lambda: client.get(f"/api/v1/benchmarks/runs/{run_id}", headers=headers).json()[
                    "data"
                ],
                {"completed"},
            )
            assert data["accuracy"] in (0.5, 0.75)

        curve = client.get(f"/api/v1/benchmarks/learning-curve/{suite_id}", headers=headers).json()[
            "data"
        ]
        assert len(curve["data"]) == 2
        assert curve["trends"]["accuracy_growth_rate"] == 0.5

    def test_learning_curve_empty_history(self, api):
        client, headers, _, _ = api
        suite_id = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        ).json()["data"]["id"]
        curve = client.get(f"/api/v1/benchmarks/learning-curve/{suite_id}", headers=headers).json()[
            "data"
        ]
        assert curve["data"] == []
        assert curve["trends"]["accuracy_growth_rate"] is None

    def test_run_passes_model_and_decrypted_key_to_executor(self, api):
        client, headers, key_id, _ = api
        suite_id = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        ).json()["data"]["id"]
        FakeBenchmarkExecutor.last_config = None
        started = client.post(
            f"/api/v1/benchmarks/suites/{suite_id}/run",
            headers=headers,
            json={
                "api_key_id": key_id,
                "dataset_path": "problems.json",
                "model": "gpt-test",
                "strategies": [{"name": "vanilla"}],
            },
        )
        assert started.status_code == 202
        run_id = started.json()["data"]["id"]
        _wait_status(
            lambda: client.get(f"/api/v1/benchmarks/runs/{run_id}", headers=headers).json()["data"],
            {"completed"},
        )
        assert FakeBenchmarkExecutor.last_config is not None
        assert FakeBenchmarkExecutor.last_config.llm_config.model == "gpt-test"
        assert FakeBenchmarkExecutor.last_config.llm_config.api_key.get_secret_value() == KEY

    def test_duplicate_suite_name_rejected(self, api):
        client, headers, _, _ = api
        first = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        )
        assert first.status_code == 201
        second = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        )
        assert second.status_code == 400
        assert "already exists" in second.json()["detail"]

    def test_suite_cross_user_access_is_404(self, api):
        client, headers, _, _ = api
        suite_id = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        ).json()["data"]["id"]
        client.post(
            "/api/v1/auth/register",
            json={"username": "dave", "email": "dave@example.org", "password": PASSWORD},
        )
        dave = client.post(
            "/api/v1/auth/login", json={"username": "dave", "password": PASSWORD}
        ).json()["data"]
        response = client.get(
            f"/api/v1/benchmarks/suites/{suite_id}",
            headers={"Authorization": "Bearer " + dave["access_token"]},
        )
        assert response.status_code == 404

    def test_run_rejects_foreign_key(self, api):
        client, headers, _, _ = api
        suite_id = client.post(
            "/api/v1/benchmarks/suites", headers=headers, json=self._suite_payload()
        ).json()["data"]["id"]
        client.post(
            "/api/v1/auth/register",
            json={"username": "bob", "email": "bob@example.org", "password": PASSWORD},
        )
        bob = client.post(
            "/api/v1/auth/login", json={"username": "bob", "password": PASSWORD}
        ).json()["data"]
        bob_key = client.post(
            "/api/v1/api-keys",
            headers={"Authorization": "Bearer " + bob["access_token"]},
            json={"provider": "openai", "key_name": "b", "api_key": KEY},
        ).json()["data"]["id"]

        response = client.post(
            f"/api/v1/benchmarks/suites/{suite_id}/run",
            headers=headers,
            json={
                "api_key_id": bob_key,
                "dataset_path": "problems.json",
                "model": "gpt-test",
            },
        )
        assert response.status_code == 404


class TestABTests:
    def _ab_payload(self, key_id):
        return {
            "name": "prompt-a-vs-b",
            "dataset_path": "problems.json",
            "model": {"model": "gpt-test"},
            "strategy": {"name": "vanilla"},
            "prompt_variants": [
                {"id": "baseline", "prefix": "Answer:"},
                {"id": "treatment", "prefix": "Think step by step:"},
            ],
            "api_key_id": key_id,
        }

    def test_ab_test_lifecycle(self, api):
        client, headers, key_id, _ = api
        created = client.post("/api/v1/ab-tests", headers=headers, json=self._ab_payload(key_id))
        assert created.status_code == 201, created.text
        test_id = created.json()["data"]["id"]

        started = client.post(f"/api/v1/ab-tests/{test_id}/run", headers=headers)
        assert started.status_code == 202, started.text
        data = _wait_status(
            lambda: client.get(f"/api/v1/ab-tests/{test_id}", headers=headers).json()["data"],
            {"completed"},
        )
        results = client.get(f"/api/v1/ab-tests/{test_id}/results", headers=headers)
        assert results.status_code == 200
        assert results.json()["data"]["variants"] == ["baseline", "treatment"]

    def test_ab_test_cross_user_access_is_404(self, api):
        client, headers, key_id, _ = api
        test_id = client.post(
            "/api/v1/ab-tests", headers=headers, json=self._ab_payload(key_id)
        ).json()["data"]["id"]
        client.post(
            "/api/v1/auth/register",
            json={"username": "erin", "email": "erin@example.org", "password": PASSWORD},
        )
        erin = client.post(
            "/api/v1/auth/login", json={"username": "erin", "password": PASSWORD}
        ).json()["data"]
        response = client.get(
            f"/api/v1/ab-tests/{test_id}",
            headers={"Authorization": "Bearer " + erin["access_token"]},
        )
        assert response.status_code == 404

    def test_ab_test_duplicate_variant_ids_rejected(self, api):
        client, headers, key_id, _ = api
        payload = self._ab_payload(key_id)
        payload["prompt_variants"][1]["id"] = "baseline"
        response = client.post("/api/v1/ab-tests", headers=headers, json=payload)
        assert response.status_code == 400


class TestAnalysis:
    def test_pareto_analyze_rejects_conflicting_experiments(self, api):
        client, headers, _, _ = api
        payload = {
            "comparisons": [
                {"experiment": {"experiment_id": "same-id"}},
                {"experiment": {"experiment_id": "same-id"}},
            ]
        }
        response = client.post("/api/v1/pareto/analyze", headers=headers, json=payload)
        assert response.status_code == 400

    def test_optimize_returns_advisory(self, api):
        client, headers, _, _ = api
        response = client.post("/api/v1/optimize", headers=headers, json={"comparison": {}})
        assert response.status_code == 200
        assert "ranking" in response.json()["data"]

    def test_analysis_requires_authentication(self, api):
        client, _, _, _ = api
        assert client.post("/api/v1/pareto/analyze", json={"comparisons": [{}]}).status_code != 200
