"""API tests for owner-scoped evaluation result queries."""

import secrets
import uuid
from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.auth.config import AuthSettings
from api.db.engine import make_engine, make_session_factory
from api.db.models import BenchmarkRun, BenchmarkSuite, Evaluation, EvaluationResult, Problem
from api.files.config import FileSettings
from api.main import create_app
from src.reporting.capability_profiler import ALL_DIMENSIONS

PASSWORD = "a-long-test-password-!"


def auth_config(tmp_path):
    return AuthSettings(
        _env_file=None,
        SECRET_KEY=secrets.token_urlsafe(48),
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        AUTH_DATABASE_PATH=tmp_path / "auth.sqlite3",
    )


def _seed(database_url: str, owner_id: str) -> None:
    """Insert the two Task 2 evaluations into the app's business database."""
    session_factory = make_session_factory(make_engine(database_url))
    with session_factory() as db:
        db.add(
            Problem(
                id="p1",
                problem_id="two-sum",
                title="Two Sum",
                difficulty="easy",
                tags=["array"],
            )
        )
        db.add_all(
            [
                Evaluation(
                    id="eval-own",
                    user_id=owner_id,
                    run_id="run-own",
                    status="completed",
                    strategy_names=["vanilla", "retry"],
                    problem_ids=["two-sum"],
                    model="gpt-test",
                    created_at=datetime(2026, 10, 1, 0, 0, 0),
                    completed_at=datetime(2026, 10, 1, 1, 0, 0),
                ),
                Evaluation(
                    id="eval-other",
                    user_id="other",
                    run_id="run-other",
                    status="completed",
                    strategy_names=["vanilla"],
                    problem_ids=["two-sum"],
                    model="gpt-test",
                ),
            ]
        )
        db.add_all(
            [
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 10,
                        "execution_time_seconds": 1.0,
                        "cost_usd": 0.2,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 1,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="retry",
                    status="failed",
                    metrics={
                        "success": False,
                        "total_tokens": 30,
                        "execution_time_seconds": 3.0,
                        "cost_usd": 9.0,
                        "cost_unknown": True,
                        "difficulty": "easy",
                    },
                    error_message="boom",
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-other",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "iterations": 1,
                        "total_tokens": 1,
                        "cost_usd": 1,
                        "cost_unknown": False,
                    },
                ),
            ]
        )
        db.commit()


@pytest.fixture
def results_api(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'biz.sqlite3'}"
    app = create_app(
        auth_config(tmp_path),
        FileSettings(_env_file=None, UPLOAD_DIR=tmp_path / "uploads"),
        database_url=database_url,
    )
    with TestClient(app) as test_client:
        register = test_client.post(
            "/api/v1/auth/register",
            json={"username": "alice", "email": "alice@example.org", "password": PASSWORD},
        )
        assert register.status_code == 201, register.text
        tokens = test_client.post(
            "/api/v1/auth/login", json={"username": "alice", "password": PASSWORD}
        ).json()["data"]
        headers = {"Authorization": "Bearer " + tokens["access_token"]}
        _seed(database_url, register.json()["data"]["id"])
        yield test_client, headers


@pytest.fixture
def client(results_api):
    return results_api[0]


@pytest.fixture
def owner_headers(results_api):
    return results_api[1]


def _install_analytics_rows(client) -> None:
    """Replace run-own with 3 successes and 1 historical failure.

    One success costs 0.2 USD. Another success is cost_unknown with cost_usd 9.
    The failure omits metrics.iterations. A running evaluation of the same user
    must stay outside the completed-only scope.
    """
    session_factory = client.app.state.task_session_factory
    with session_factory() as db:
        owner = db.scalar(select(Evaluation).where(Evaluation.id == "eval-own"))
        assert owner is not None
        stored = list(
            db.scalars(
                select(EvaluationResult).where(EvaluationResult.evaluation_id == "eval-own")
            ).all()
        )
        for row in stored:
            db.delete(row)
        db.add(
            Evaluation(
                id="eval-open",
                user_id=owner.user_id,
                run_id="run-open",
                status="running",
                strategy_names=["vanilla"],
                problem_ids=["two-sum"],
                model="gpt-test",
            )
        )
        db.add_all(
            [
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 10,
                        "execution_time_seconds": 1.0,
                        "cost_usd": 0.2,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 1,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="retry",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 20,
                        "execution_time_seconds": 2.0,
                        "cost_usd": 9,
                        "cost_unknown": True,
                        "difficulty": "easy",
                        "iterations": 2,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="reflect",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 30,
                        "execution_time_seconds": 3.0,
                        "cost_usd": 0,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 3,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="failed",
                    metrics={
                        "success": False,
                        "total_tokens": 40,
                        "execution_time_seconds": 4.0,
                        "difficulty": "easy",
                    },
                    error_message="boom",
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-open",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 1,
                        "execution_time_seconds": 9.0,
                        "cost_usd": 5,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 9,
                    },
                ),
            ]
        )
        db.commit()


def test_analytics_match_stored_rows(client, owner_headers):
    _install_analytics_rows(client)
    rate = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert rate.status_code == 200
    assert rate.json()["data"]["success_rate"] == 0.75
    assert rate.json()["data"]["solved"] == 3
    assert rate.json()["data"]["total"] == 4
    assert rate.json()["data"]["avg_execution_time"] == 2.5
    assert rate.json()["data"]["by_difficulty"] == {
        "easy": {"success_rate": 0.75, "solved": 3, "total": 4}
    }
    assert rate.json()["data"]["by_tag"] == {
        "array": {"success_rate": 0.75, "solved": 3, "total": 4}
    }
    scoped = client.get("/api/v1/analytics/success-rate", headers=owner_headers)
    assert scoped.status_code == 200
    assert scoped.json()["data"]["solved"] == 3
    assert scoped.json()["data"]["total"] == 4
    running = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-open"}
    )
    assert running.status_code == 200
    assert running.json()["data"]["solved"] == 1
    assert running.json()["data"]["total"] == 1
    missing = client.get(
        "/api/v1/analytics/success-rate", headers=owner_headers, params={"run_id": "run-other"}
    )
    assert missing.status_code == 404
    tokens = client.get(
        "/api/v1/analytics/tokens", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert tokens.json()["data"]["total_tokens"] == 100
    assert tokens.json()["data"]["avg_tokens"] == 25
    assert tokens.json()["data"]["estimated_cost_usd"] == 0.2
    assert tokens.json()["data"]["unknown_cost_count"] == 1
    modes = client.get(
        "/api/v1/analytics/failure-modes", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert modes.status_code == 200
    assert modes.json()["data"] == {"unknown": 1}
    iterations = client.get(
        "/api/v1/analytics/iterations", headers=owner_headers, params={"run_id": "run-own"}
    )
    payload = iterations.json()["data"]
    assert payload["average"] == 2
    assert payload["distribution"] == [
        {"iterations": 1, "count": 1},
        {"iterations": 2, "count": 1},
        {"iterations": 3, "count": 1},
    ]
    assert payload["unknown_count"] == 1
    assert payload["known_count"] == 3


def _unit(status: str, cost: float, *, unknown: bool = False) -> dict:
    """Hand-built unit metrics. cost_unknown rows must not enter the USD sum."""
    return {
        "success": status == "success",
        "total_tokens": 10,
        "execution_time_seconds": 1.0,
        "cost_usd": cost,
        "cost_unknown": unknown,
        "difficulty": "easy",
        "iterations": 1,
    }


def _insert_run(
    client,
    *,
    evaluation_id: str,
    run_id: str,
    model: str,
    strategy_names: list[str],
    status: str,
    completed_at: datetime | None,
    units: list[tuple[str, str, dict]],
) -> None:
    """Insert one evaluation and its units for the seeded owner."""
    session_factory = client.app.state.task_session_factory
    with session_factory() as db:
        owner = db.scalar(select(Evaluation).where(Evaluation.id == "eval-own"))
        assert owner is not None
        db.add(
            Evaluation(
                id=evaluation_id,
                user_id=owner.user_id,
                run_id=run_id,
                status=status,
                strategy_names=strategy_names,
                problem_ids=["two-sum"],
                model=model,
                created_at=completed_at or datetime(2026, 10, 1),
                completed_at=completed_at,
            )
        )
        for strategy_name, unit_status, metrics in units:
            db.add(
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id=evaluation_id,
                    problem_id="two-sum",
                    strategy_name=strategy_name,
                    status=unit_status,
                    metrics=metrics,
                )
            )
        db.commit()


def _strategy_numbers(items: list[dict]) -> dict[str, tuple]:
    return {
        item["name"]: (
            item["success_rate"],
            item["solved_problems"],
            item["estimated_cost_usd"],
        )
        for item in items
    }


def test_compare_matches_detail_and_empty_history(client, owner_headers):
    detail = client.get("/api/v1/results/run-own", headers=owner_headers).json()["data"]
    compared = client.get(
        "/api/v1/compare/strategies", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert compared.status_code == 200
    by_name = {item["name"]: item for item in detail["strategies"]}
    for item in compared.json()["data"]["strategies"]:
        assert item["success_rate"] == by_name[item["name"]]["success_rate"]
        assert item["solved_problems"] == by_name[item["name"]]["solved_problems"]
        assert item["estimated_cost_usd"] == by_name[item["name"]]["estimated_cost_usd"]
    assert _strategy_numbers(compared.json()["data"]["strategies"]) == {
        "vanilla": (1.0, 1, 0.2),
        "retry": (0.0, 0, 0.0),
    }
    missing_run = client.get("/api/v1/compare/strategies", headers=owner_headers)
    assert missing_run.status_code == 400
    history = client.get(
        "/api/v1/compare/history", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert history.status_code == 200
    assert history.json()["data"]["series"] == []
    missing = client.get("/api/v1/compare/ab-test/missing", headers=owner_headers)
    assert missing.status_code == 404

    _insert_run(
        client,
        evaluation_id="eval-alt",
        run_id="run-alt",
        model="claude-test",
        strategy_names=["retry", "vanilla"],
        status="completed",
        completed_at=datetime(2026, 10, 2, 0, 0, 0),
        units=[
            ("vanilla", "failed", _unit("failed", 1.0)),
            ("retry", "success", _unit("success", 0.4)),
        ],
    )
    models = client.get("/api/v1/compare/models", headers=owner_headers)
    assert models.status_code == 200
    grouped = {item["model"]: item["strategies"] for item in models.json()["data"]["models"]}
    assert set(grouped) == {"gpt-test", "claude-test"}
    own_detail = client.get("/api/v1/results/run-own", headers=owner_headers).json()["data"]
    alt_detail = client.get("/api/v1/results/run-alt", headers=owner_headers).json()["data"]
    assert _strategy_numbers(grouped["gpt-test"]) == _strategy_numbers(own_detail["strategies"])
    assert _strategy_numbers(grouped["claude-test"]) == _strategy_numbers(alt_detail["strategies"])
    assert _strategy_numbers(grouped["claude-test"]) == {
        "vanilla": (0.0, 0, 1.0),
        "retry": (1.0, 1, 0.4),
    }
    still_empty = client.get(
        "/api/v1/compare/history", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert still_empty.status_code == 200
    assert still_empty.json()["data"]["series"] == []

    _insert_run(
        client,
        evaluation_id="eval-early",
        run_id="run-match-early",
        model="gpt-test",
        strategy_names=["retry", "vanilla"],
        status="completed",
        completed_at=datetime(2026, 9, 15),
        units=[
            ("vanilla", "success", _unit("success", 0.1)),
            ("retry", "failed", _unit("failed", 8.0, unknown=True)),
        ],
    )
    _insert_run(
        client,
        evaluation_id="eval-late",
        run_id="run-match-late",
        model="gpt-test",
        strategy_names=["vanilla", "retry"],
        status="completed",
        completed_at=datetime(2026, 11, 2, 3, 0, 0),
        units=[
            ("vanilla", "failed", _unit("failed", 0.3)),
            ("retry", "success", _unit("success", 0.7)),
        ],
    )
    _insert_run(
        client,
        evaluation_id="eval-other-strategies",
        run_id="run-other-strategies",
        model="gpt-test",
        strategy_names=["vanilla"],
        status="completed",
        completed_at=datetime(2026, 10, 15),
        units=[("vanilla", "success", _unit("success", 2.0))],
    )
    _insert_run(
        client,
        evaluation_id="eval-running-same",
        run_id="run-running-same",
        model="gpt-test",
        strategy_names=["vanilla", "retry"],
        status="running",
        completed_at=datetime(2026, 10, 20),
        units=[
            ("vanilla", "success", _unit("success", 4.0)),
            ("retry", "success", _unit("success", 4.0)),
        ],
    )
    series = client.get(
        "/api/v1/compare/history", headers=owner_headers, params={"run_id": "run-own"}
    )
    assert series.status_code == 200
    points = series.json()["data"]["series"]
    assert [point["run_id"] for point in points] == ["run-match-early", "run-match-late"]
    assert [point["completed_at"] for point in points] == [
        "2026-09-15T00:00:00Z",
        "2026-11-02T03:00:00Z",
    ]
    assert _strategy_numbers(points[0]["strategies"]) == {
        "vanilla": (1.0, 1, 0.1),
        "retry": (0.0, 0, 0.0),
    }
    assert _strategy_numbers(points[1]["strategies"]) == {
        "vanilla": (0.0, 0, 0.3),
        "retry": (1.0, 1, 0.7),
    }
    from_early = client.get(
        "/api/v1/compare/history", headers=owner_headers, params={"run_id": "run-match-early"}
    )
    assert [point["run_id"] for point in from_early.json()["data"]["series"]] == [
        "run-own",
        "run-match-late",
    ]


def _points_by_name(payload: dict) -> dict[str, dict]:
    return {point["name"]: point for point in payload["points"]}


def _install_learning_curve_rows(client) -> None:
    """Completed benchmark runs for the owner, plus rows the curve must skip."""
    session_factory = client.app.state.task_session_factory
    with session_factory() as db:
        owner = db.scalar(select(Evaluation).where(Evaluation.id == "eval-own"))
        assert owner is not None
        db.add_all(
            [
                BenchmarkSuite(
                    id="suite-a",
                    user_id=owner.user_id,
                    name="suite-a",
                    problems=["two-sum"],
                ),
                BenchmarkSuite(
                    id="suite-b",
                    user_id=owner.user_id,
                    name="suite-b",
                    problems=["two-sum"],
                ),
            ]
        )
        db.flush()
        db.add_all(
            [
                BenchmarkRun(
                    id="bench-late",
                    suite_id="suite-a",
                    user_id=owner.user_id,
                    status="completed",
                    model="gpt-test",
                    accuracy=0.5,
                    cost_usd=1.5,
                    completed_at=datetime(2026, 10, 2),
                ),
                BenchmarkRun(
                    id="bench-early",
                    suite_id="suite-a",
                    user_id=owner.user_id,
                    status="completed",
                    model="claude-test",
                    accuracy=0.25,
                    cost_usd=0.5,
                    completed_at=datetime(2026, 9, 1),
                ),
                BenchmarkRun(
                    id="bench-z",
                    suite_id="suite-a",
                    user_id=owner.user_id,
                    status="completed",
                    model="gpt-test",
                    accuracy=0.75,
                    cost_usd=0.75,
                    completed_at=datetime(2026, 11, 1),
                ),
                BenchmarkRun(
                    id="bench-a",
                    suite_id="suite-a",
                    user_id=owner.user_id,
                    status="completed",
                    model="gpt-test",
                    accuracy=0.125,
                    cost_usd=0.25,
                    completed_at=datetime(2026, 11, 1),
                ),
                BenchmarkRun(
                    id="bench-other-suite",
                    suite_id="suite-b",
                    user_id=owner.user_id,
                    status="completed",
                    model="gpt-test",
                    accuracy=1.0,
                    cost_usd=2.0,
                    completed_at=datetime(2026, 8, 1),
                ),
                BenchmarkRun(
                    id="bench-pending",
                    suite_id="suite-a",
                    user_id=owner.user_id,
                    status="pending",
                    model="hidden-pending",
                    accuracy=0.9,
                    cost_usd=9.0,
                    completed_at=datetime(2026, 7, 1),
                ),
                BenchmarkRun(
                    id="bench-other-user",
                    suite_id="suite-a",
                    user_id="other",
                    status="completed",
                    model="hidden-other",
                    accuracy=1.0,
                    cost_usd=3.0,
                    completed_at=datetime(2026, 6, 1),
                ),
            ]
        )
        db.commit()


def test_radar_and_empty_learning_curve(client, owner_headers):
    detail = client.get("/api/v1/results/run-own", headers=owner_headers).json()["data"]
    by_name = {item["name"]: item for item in detail["strategies"]}

    radar = client.get(
        "/api/v1/visualizations/capability-radar",
        headers=owner_headers,
        params={"run_id": "run-own"},
    )
    assert radar.status_code == 200
    data = radar.json()["data"]
    assert data["dimensions"] == ALL_DIMENSIONS
    assert data["series"][0]["name"] == "gpt-test"
    assert len(data["series"]) == 1
    assert data["series"][0]["data"] == [50.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    assert all(0 <= score <= 100 for score in data["series"][0]["data"])
    assert set(data["problem_counts"]) == set(ALL_DIMENSIONS)
    assert data["problem_counts"] == {
        "Array": 1,
        "Graph": 0,
        "Dynamic Programming": 0,
        "Greedy": 0,
        "Math": 0,
        "String": 0,
        "Other": 0,
    }

    success = client.get(
        "/api/v1/visualizations/success-rate-chart",
        headers=owner_headers,
        params={"run_id": "run-own"},
    )
    assert success.status_code == 200
    success_points = _points_by_name(success.json()["data"])
    assert {name: point["success_rate"] for name, point in success_points.items()} == {
        name: item["success_rate"] for name, item in by_name.items()
    }
    assert {name: point["success_rate"] for name, point in success_points.items()} == {
        "vanilla": 1.0,
        "retry": 0.0,
    }

    token = client.get(
        "/api/v1/visualizations/token-chart",
        headers=owner_headers,
        params={"run_id": "run-own"},
    )
    assert token.status_code == 200
    lines = {line["name"]: line["points"] for line in token.json()["data"]["series"]}
    expected_lines: dict[str, list[dict]] = {}
    for item in detail["problems"]["items"]:
        expected_lines.setdefault(item["strategy"], []).append(
            {"problem_id": item["problem_id"], "tokens": item["tokens"]}
        )
    assert lines == expected_lines
    assert lines == {
        "vanilla": [{"problem_id": "two-sum", "tokens": 10}],
        "retry": [{"problem_id": "two-sum", "tokens": 30}],
    }

    cost = client.get(
        "/api/v1/visualizations/cost-accuracy",
        headers=owner_headers,
        params={"run_id": "run-own"},
    )
    assert cost.status_code == 200
    cost_points = _points_by_name(cost.json()["data"])
    assert {name: point["estimated_cost_usd"] for name, point in cost_points.items()} == {
        name: item["estimated_cost_usd"] for name, item in by_name.items()
    }
    assert {name: point["success_rate"] for name, point in cost_points.items()} == {
        name: item["success_rate"] for name, item in by_name.items()
    }
    assert {name: point["estimated_cost_usd"] for name, point in cost_points.items()} == {
        "vanilla": 0.2,
        "retry": 0.0,
    }

    vanilla = client.get(
        "/api/v1/visualizations/success-rate-chart",
        headers=owner_headers,
        params={"run_id": "run-own", "strategy": "vanilla"},
    )
    assert _points_by_name(vanilla.json()["data"]) == {
        "vanilla": {"name": "vanilla", "success_rate": 1.0}
    }
    empty_tag = client.get(
        "/api/v1/visualizations/success-rate-chart",
        headers=owner_headers,
        params={"run_id": "run-own", "tag": "graph"},
    )
    assert empty_tag.status_code == 200
    assert empty_tag.json()["data"]["points"] == []
    missing = client.get(
        "/api/v1/visualizations/success-rate-chart",
        headers=owner_headers,
        params={"run_id": "run-other"},
    )
    assert missing.status_code == 404

    curve = client.get("/api/v1/visualizations/learning-curve", headers=owner_headers)
    assert curve.status_code == 200
    assert curve.json()["data"]["series"] == []

    _install_learning_curve_rows(client)
    filled = client.get("/api/v1/visualizations/learning-curve", headers=owner_headers)
    assert filled.status_code == 200
    series = filled.json()["data"]["series"]
    assert [(point["suite_id"], point["timestamp"], point["model"]) for point in series] == [
        ("suite-b", "2026-08-01T00:00:00Z", "gpt-test"),
        ("suite-a", "2026-09-01T00:00:00Z", "claude-test"),
        ("suite-a", "2026-10-02T00:00:00Z", "gpt-test"),
        ("suite-a", "2026-11-01T00:00:00Z", "gpt-test"),
        ("suite-a", "2026-11-01T00:00:00Z", "gpt-test"),
    ]
    assert [(point["accuracy"], point["cost_usd"]) for point in series] == [
        (1.0, 2.0),
        (0.25, 0.5),
        (0.5, 1.5),
        (0.125, 0.25),
        (0.75, 0.75),
    ]
    assert all(point["model"] not in {"hidden-pending", "hidden-other"} for point in series)
    narrowed = client.get(
        "/api/v1/visualizations/learning-curve",
        headers=owner_headers,
        params={"suite_id": "suite-a"},
    )
    assert [point["suite_id"] for point in narrowed.json()["data"]["series"]] == ["suite-a"] * 4
    assert [point["accuracy"] for point in narrowed.json()["data"]["series"]] == [
        0.25,
        0.5,
        0.125,
        0.75,
    ]

    _insert_run(
        client,
        evaluation_id="eval-open-chart",
        run_id="run-open-chart",
        model="gpt-draft",
        strategy_names=["draft"],
        status="running",
        completed_at=None,
        units=[("draft", "success", _unit("success", 3.0))],
    )
    running = client.get(
        "/api/v1/visualizations/success-rate-chart",
        headers=owner_headers,
        params={"run_id": "run-open-chart"},
    )
    assert _points_by_name(running.json()["data"]) == {
        "draft": {"name": "draft", "success_rate": 1.0}
    }
    scoped = client.get("/api/v1/visualizations/success-rate-chart", headers=owner_headers)
    assert set(_points_by_name(scoped.json()["data"])) == {"vanilla", "retry"}
    draft_radar = client.get(
        "/api/v1/visualizations/capability-radar",
        headers=owner_headers,
        params={"run_id": "run-open-chart"},
    )
    assert draft_radar.json()["data"]["series"][0]["name"] == "gpt-draft"


def test_results_api_hides_other_users_and_paginates_problems(client, owner_headers):
    own = client.get("/api/v1/results/run-own", headers=owner_headers, params={"limit": 1})
    assert own.status_code == 200
    body = own.json()
    assert body["success"] is True
    assert body["data"]["strategies"][0]["total_problems"] >= 1
    assert body["data"]["problems"]["total"] == 2
    assert len(body["data"]["problems"]["items"]) == 1
    missing = client.get("/api/v1/results/eval-other", headers=owner_headers)
    assert missing.status_code == 404
    listed = client.get("/api/v1/results", headers=owner_headers, params={"tag": "array"})
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1
    assert listed.json()["data"]["items"][0]["run_id"] == "run-own"
    anon = client.get("/api/v1/results/run-own")
    assert anon.status_code == 401
