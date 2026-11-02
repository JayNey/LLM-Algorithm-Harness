"""Issue #329: real HTTP analytics against isolated SQLite, Redis, API and Vite.

Seeds one completed run whose results exercise the #318 execution-metadata
semantics (personal problem, personal override of a public ID, explicit empty
tags, legacy rows without a snapshot), plus sibling runs for history and model
comparison. Asserts the analytics contract over real TCP HTTP, then drives the
real results pages in Chromium with cookie login and no route stubs. No provider
calls, worker execution, existing accounts or databases are used.
"""

from __future__ import annotations

import json
import os
import secrets
import subprocess
import sys
import tempfile
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from cryptography.fernet import Fernet
from verify_frontend_first_batch import ROOT, free_port, stop, wait_http

OWNER = "analyticsowner"
RUN_EVAL, RUN_ID = "f3-run", "f3-run-id"
HISTORY_EVAL, HISTORY_ID = "f3-history", "f3-history-id"
OTHER_EVAL, OTHER_ID = "f3-other", "f3-other-id"
MODEL, OTHER_MODEL = "local-model", "other-model"
DIMENSIONS = ["Array", "Graph", "Dynamic Programming", "Greedy", "Math", "String", "Other"]


def snapshot(tags: list[str], difficulty: str | None, origin: str = "personal") -> dict:
    return {
        "schema_version": 1,
        "origin": origin,
        "tags": tags,
        "difficulty": difficulty,
        "source_platform": None,
        "source_problem_id": None,
        "source_url": None,
        "source_version": None,
        "source_metadata": {},
    }


def metrics(
    *,
    success: bool,
    tokens: int | None = 100,
    iterations: int | None = 1,
    cost_unknown: bool = False,
    snap: dict | None = None,
    failure: tuple[str, str] | None = None,
) -> dict:
    data: dict = {
        "success": success,
        "total_tokens": tokens,
        "iterations": iterations,
        "cost_usd": 0.0 if cost_unknown else 0.01,
        "cost_unknown": cost_unknown,
        "execution_time_seconds": 0.5,
    }
    if snap is not None:
        data["problem_snapshot"] = snap
        data["difficulty"] = snap["difficulty"]
    if failure:
        data["failure_mode"], data["failure_category"] = failure
    return data


# (problem_id, strategy, status, metrics, error_message)
RUN_UNITS = [
    (
        "personal-dp",
        "direct",
        "success",
        metrics(success=True, snap=snapshot(["dynamic-programming"], "hard")),
        None,
    ),
    (
        "personal-dp",
        "cot",
        "failed",
        metrics(
            success=False,
            cost_unknown=True,
            snap=snapshot(["dynamic-programming"], "hard"),
            failure=("logic_error", "wrong_answer"),
        ),
        "assert 1 == 2",
    ),
    # Public row says graph/medium; the executed personal version says array/easy.
    (
        "shared-graph",
        "direct",
        "success",
        metrics(success=True, snap=snapshot(["array"], "easy")),
        None,
    ),
    (
        "empty-tags",
        "direct",
        "failed",
        metrics(success=False, snap=snapshot([], None), failure=("timeout", "system_error")),
        None,
    ),
    # Legacy row without snapshot falls back to the live public problem (math/medium).
    ("legacy-sum", "direct", "success", metrics(success=True), None),
    # Legacy row whose public problem no longer exists: counted, but no tag or dimension.
    ("legacy-missing", "cot", "success", metrics(success=True, tokens=None, iterations=None), None),
]
EXPECTED = {
    "success_rate": {"solved": 4, "total": 6},
    "by_tag": {"dynamic-programming": (1, 2), "array": (1, 1), "math": (1, 1)},
    "by_difficulty": {"hard": (1, 2), "easy": (1, 1), "medium": (1, 1)},
    "tokens": {"total_tokens": 500.0, "unknown_cost_count": 1, "estimated_cost_usd": 0.05},
    "iterations": {"known_count": 5, "unknown_count": 1, "average": 1.0},
    "failure_modes": {"logic_error": 1, "timeout": 1},
    "radar": {
        "Dynamic Programming": (50.0, 1),
        "Array": (100.0, 1),
        "Math": (100.0, 1),
        "Graph": (0.0, 0),
    },
    "failure_cases": 2,
    "clusters": [{"pattern": "assert N == N", "count": 1}],
    "strategies": {"direct": (3, 4), "cot": (1, 2)},
    "history_run_ids": [HISTORY_ID],
    "models": sorted([MODEL, OTHER_MODEL]),
}


def seed(database_url: str, owner: str) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from api.db.models import Evaluation, EvaluationResult, Problem

    engine = create_engine(database_url)
    base_time = datetime(2026, 10, 1, tzinfo=timezone.utc).replace(tzinfo=None)
    with Session(engine) as db:
        db.add(
            Problem(
                id="pub-graph",
                problem_id="shared-graph",
                title="Shared graph",
                difficulty="medium",
                tags=["graph"],
            )
        )
        db.add(
            Problem(
                id="pub-sum",
                problem_id="legacy-sum",
                title="Legacy sum",
                difficulty="medium",
                tags=["math"],
            )
        )
        runs = [
            (RUN_EVAL, RUN_ID, MODEL, ["direct", "cot"], base_time + timedelta(days=2)),
            (HISTORY_EVAL, HISTORY_ID, MODEL, ["direct", "cot"], base_time + timedelta(days=1)),
            (OTHER_EVAL, OTHER_ID, OTHER_MODEL, ["direct"], base_time),
        ]
        for eval_id, run_id, model, strategies, completed_at in runs:
            db.add(
                Evaluation(
                    id=eval_id,
                    user_id=owner,
                    run_id=run_id,
                    status="completed",
                    strategy_names=strategies,
                    problem_ids=(
                        sorted({unit[0] for unit in RUN_UNITS})
                        if eval_id == RUN_EVAL
                        else ["legacy-sum"]
                    ),
                    problem_count=3 if eval_id == RUN_EVAL else 1,
                    completed_count=4 if eval_id == RUN_EVAL else len(strategies),
                    failed_count=2 if eval_id == RUN_EVAL else 0,
                    model=model,
                    created_at=completed_at - timedelta(hours=1),
                    started_at=completed_at - timedelta(hours=1),
                    completed_at=completed_at,
                )
            )
        db.flush()
        for index, (problem_id, strategy, status, unit_metrics, error) in enumerate(RUN_UNITS):
            db.add(
                EvaluationResult(
                    id=f"f3-unit-{index}",
                    evaluation_id=RUN_EVAL,
                    problem_id=problem_id,
                    strategy_name=strategy,
                    status=status,
                    metrics=unit_metrics,
                    error_message=error,
                    created_at=base_time + timedelta(days=2, minutes=index),
                )
            )
        for eval_id, strategies in ((HISTORY_EVAL, ["direct", "cot"]), (OTHER_EVAL, ["direct"])):
            for strategy in strategies:
                db.add(
                    EvaluationResult(
                        id=f"{eval_id}-{strategy}",
                        evaluation_id=eval_id,
                        problem_id="legacy-sum",
                        strategy_name=strategy,
                        status="success",
                        metrics=metrics(success=True),
                    )
                )
        db.commit()
    engine.dispose()


def assert_contract(client: httpx.Client) -> list[str]:
    checks: list[str] = []
    run = {"run_id": RUN_ID}

    def data(path: str, params: dict | None = None) -> dict:
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()["data"]

    rate = data("/analytics/success-rate", run)
    assert (rate["solved"], rate["total"]) == (4, 6), rate
    assert {k: (v["solved"], v["total"]) for k, v in rate["by_tag"].items()} == EXPECTED[
        "by_tag"
    ], rate["by_tag"]
    assert {k: (v["solved"], v["total"]) for k, v in rate["by_difficulty"].items()} == EXPECTED[
        "by_difficulty"
    ]
    checks.append(
        "success-rate: snapshot tags win over public row, empty tags and missing legacy stay untagged"
    )
    tokens = data("/analytics/tokens", run)
    assert tokens["unknown_cost_count"] == 1 and tokens["total_tokens"] == 500.0, tokens
    assert abs(tokens["estimated_cost_usd"] - 0.05) < 1e-9, tokens
    checks.append("tokens: unknown cost counted, known cost excludes unknown unit")
    iterations = data("/analytics/iterations", run)
    assert (iterations["known_count"], iterations["unknown_count"], iterations["average"]) == (
        5,
        1,
        1.0,
    )
    checks.append("iterations: null stays unknown")
    assert data("/analytics/failure-modes", run) == EXPECTED["failure_modes"]
    checks.append("failure-modes")
    radar = data("/visualizations/capability-radar", run)
    assert radar["dimensions"] == DIMENSIONS and [s["name"] for s in radar["series"]] == [
        MODEL
    ], radar
    scores = dict(zip(radar["dimensions"], radar["series"][0]["data"]))
    for dimension, (score, count) in EXPECTED["radar"].items():
        assert scores[dimension] == score and radar["problem_counts"][dimension] == count, (
            dimension,
            radar,
        )
    checks.append(
        "capability-radar: dimensions from snapshot tags, versions deduped, overridden public tag ignored"
    )
    by_tag = data("/failures/by-tag", run)["tags"]
    assert {k: (v["solved"], v["total"]) for k, v in by_tag.items()} == EXPECTED["by_tag"], by_tag
    assert data("/failures/by-tag", {**run, "tag": "graph"})["tags"] == {}
    checks.append("failures/by-tag honours exact tag filter and overridden tags")
    summary = data(f"/failures/summary/{RUN_ID}")
    assert (
        summary["modes"] == EXPECTED["failure_modes"]
        and summary["clusters"] == EXPECTED["clusters"]
    ), summary
    cases = data(f"/failures/cases/{RUN_ID}")["items"]
    assert len(cases) == 2 and sorted(c["error_message"] is None for c in cases) == [
        False,
        True,
    ], cases
    checks.append("failure summary and cases match seeded failures")
    strategies = {
        s["name"]: (s["solved_problems"], s["total_problems"])
        for s in data("/compare/strategies", run)["strategies"]
    }
    assert strategies == EXPECTED["strategies"], strategies
    history = data("/compare/history", run)["series"]
    assert [h["run_id"] for h in history] == [HISTORY_ID], history
    models = sorted(m["model"] for m in data("/compare/models")["models"])
    assert models == EXPECTED["models"], models
    assert client.get("/compare/strategies").status_code == 400
    assert client.get("/analytics/success-rate", params={"run_id": "missing"}).status_code == 404
    checks.append("compare strategies/history/models and 400/404 contract")
    account = data("/analytics/success-rate")
    assert account["total"] == 9, account
    checks.append("account scope aggregates completed runs only")
    return checks


def run() -> None:
    runtime = Path(tempfile.mkdtemp(prefix="issue329-analytics-"))
    os.chmod(runtime, 0o700)
    print(f"Diagnostics: {runtime}", flush=True)
    api_port, ui_port, redis_port = free_port(), free_port(), free_port()
    api_url, ui_url = f"http://127.0.0.1:{api_port}", f"http://127.0.0.1:{ui_port}"
    password = secrets.token_urlsafe(24) + "!aA1"
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "SECRET_KEY": secrets.token_urlsafe(48),
        "ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "AUTH_DATABASE_PATH": str(runtime / "auth.sqlite3"),
        "DATABASE_URL": f"sqlite:///{runtime / 'business.sqlite3'}",
        "UPLOAD_DIR": str(runtime / "uploads"),
        "TASK_SERVICE_ROOT": str(runtime / "tasks"),
        "CORS_ORIGINS": json.dumps([ui_url]),
        "CELERY_BROKER_URL": f"redis://127.0.0.1:{redis_port}/0",
        "CELERY_RESULT_BACKEND": f"redis://127.0.0.1:{redis_port}/1",
        "AUTH_RATE_LIMIT": "100",
        "AUTH_PROTECTED_RATE_LIMIT": "10000",
        "VITE_API_BASE_URL": api_url + "/api/v1",
        "VITE_WS_URL": f"ws://127.0.0.1:{api_port}/api/v1/ws",
        "VITE_APP_NAME": "Issue 329 acceptance",
    }
    # Only the browser script needs the credentials and expectations.
    browser_env = {
        **env,
        "ANALYTICS_UI_URL": ui_url,
        "ANALYTICS_API_URL": api_url,
        "ANALYTICS_USERNAME": OWNER,
        "ANALYTICS_PASSWORD": password,
        "ANALYTICS_EVALUATION_ID": RUN_EVAL,
        "ANALYTICS_EXPECTED": json.dumps(EXPECTED),
        "ANALYTICS_OUT": str(runtime / "browser.json"),
    }
    with ExitStack() as stack:

        def launch(name: str, args: list[str], cwd: Path = runtime) -> subprocess.Popen:
            log = stack.enter_context((runtime / f"{name}.log").open("w", encoding="utf-8"))
            process = subprocess.Popen(args, cwd=cwd, env=env, stdout=log, stderr=log)
            stack.callback(stop, process)
            return process

        launch(
            "redis",
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--save",
                "",
                "--appendonly",
                "no",
            ],
        )
        api = launch(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "api.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
        )
        wait_http(api_url + "/api/v1/health", api)
        ui = launch(
            "ui",
            [
                str(ROOT / "frontend/node_modules/.bin/vite"),
                "--host",
                "127.0.0.1",
                "--port",
                str(ui_port),
                "--strictPort",
            ],
            ROOT / "frontend",
        )
        with httpx.Client(base_url=api_url + "/api/v1", timeout=15) as client:
            response = client.post(
                "/auth/register",
                json={"username": OWNER, "email": "analytics@example.test", "password": password},
            )
            response.raise_for_status()
            owner = response.json()["data"]["id"]
            seed(env["DATABASE_URL"], owner)
            response = client.post("/auth/login", json={"username": OWNER, "password": password})
            response.raise_for_status()
            checks = assert_contract(client)
        wait_http(ui_url, ui)
        subprocess.run(
            ["node", str(ROOT / "frontend/scripts/verify-results-analytics-live.mjs")],
            cwd=runtime,
            env=browser_env,
            check=True,
        )
        browser = json.loads((runtime / "browser.json").read_text(encoding="utf-8"))
        result = {
            "passed": True,
            "layer": "real TCP HTTP + SQLite + Redis + Vite + Chromium cookie login, seeded results, no provider execution",
            "api_checks": checks,
            "browser_checks": browser["checks"],
        }
        (runtime / "result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(result, ensure_ascii=False))
        print("Evidence:", runtime / "result.json")


if __name__ == "__main__":
    run()
