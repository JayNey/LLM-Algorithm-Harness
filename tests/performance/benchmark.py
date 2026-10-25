"""Isolated API/SQL benchmark and loopback Locust target. Run from repository root."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import secrets
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter

# Support `python tests/performance/benchmark.py` without installing tests as a package.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import insert

from api.auth.config import AuthSettings
from api.auth.models import RegisterInput
from api.db.models import AsyncTask, Evaluation, Problem
from api.db.problem_store import ProblemStore
from api.files.config import FileSettings
from api.main import create_app
from api.monitoring.config import MonitorSettings


def positive(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be positive")
    return value


def summary(samples, elapsed, errors):
    """Nearest-rank percentiles; durations include failed attempts, in milliseconds."""
    ordered = sorted(samples)
    if not ordered or elapsed <= 0:
        raise ValueError("nonempty samples and positive elapsed time required")
    return {
        "requests": len(samples),
        "errors": sum(errors.values()),
        "error_types": dict(errors),
        "elapsed_s": round(elapsed, 6),
        "throughput_per_s": round(len(samples) / elapsed, 3),
        "mean_ms": round(sum(ordered) / len(ordered), 3),
        **{
            f"p{p}_ms": round(ordered[math.ceil(len(ordered) * p / 100) - 1], 3)
            for p in (50, 95, 99)
        },
    }


def measure(operation, samples, concurrency=1):
    def attempt(_):
        started = perf_counter()
        error = None
        try:
            operation()
        except Exception as exc:
            # Never persist exception text (which can contain credentials or SQL values).
            error = type(exc).__name__
        return (perf_counter() - started) * 1000, error

    # Fail visibly on invalid setup and exclude warmup from the measured samples.
    for _ in range(3):
        operation()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        started = perf_counter()
        results = list(pool.map(attempt, range(samples)))
        elapsed = perf_counter() - started
    return summary(
        [duration for duration, _ in results],
        elapsed,
        Counter(error for _, error in results if error),
    )


def fixture_app(root, rows, token_file=None):
    """Real application, migrations and data; every mutable store is under root."""
    app = create_app(
        AuthSettings(
            _env_file=None,
            SECRET_KEY=secrets.token_urlsafe(48),
            ENCRYPTION_KEY=Fernet.generate_key().decode(),
            AUTH_DATABASE_PATH=root / "auth.sqlite3",
            AUTH_PROTECTED_RATE_LIMIT=10000,
            ACCESS_TOKEN_EXPIRE_MINUTES=1440,
        ),
        FileSettings(_env_file=None, UPLOAD_DIR=root / "uploads"),
        database_url=f"sqlite:///{root / 'business.sqlite3'}",
        monitor_settings=MonitorSettings(_env_file=None),
    )
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        async with original(app):
            password = secrets.token_urlsafe(32)
            owner = app.state.auth.register(
                RegisterInput(username="perf-user", email="perf@example.org", password=password)
            )["id"]
            app.state.perf_owner = owner
            app.state.perf_token = app.state.auth.login("perf-user", password)["access_token"]
            with app.state.task_session_factory.begin() as session:
                session.execute(
                    insert(Problem),
                    [
                        {"id": f"p-{i}", "problem_id": f"perf-{i:08d}", "title": f"Problem {i}"}
                        for i in range(rows)
                    ],
                )
                session.execute(
                    insert(AsyncTask),
                    [
                        {
                            "id": f"t-{i}",
                            "celery_task_id": f"c-{i}",
                            "task_type": "evaluation",
                            "entity_id": f"e-{i}",
                            "user_id": owner,
                            "status": "completed",
                        }
                        for i in range(rows)
                    ],
                )
                session.execute(
                    insert(Evaluation),
                    [
                        {
                            "id": f"e-{i}",
                            "user_id": owner,
                            "status": "completed",
                            "strategy_names": ["vanilla"],
                            "async_task_id": f"t-{i}",
                        }
                        for i in range(rows)
                    ],
                )
            if token_file:
                # Refuse to overwrite an existing file, including a symbolic link.
                fd = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(app.state.perf_token)
            try:
                yield
            finally:
                if token_file:
                    token_file.unlink(missing_ok=True)
                # create_app owns these services, but currently only closes evaluations.
                for name in ("evaluation_results", "experiments", "benchmarks", "ab_tests", "cost"):
                    getattr(app.state, name)._engine.dispose()

    app.router.lifespan_context = lifespan
    return app


def run_benchmark(rows=1000, samples=100, concurrency=4):
    with TemporaryDirectory(prefix="harness-perf-") as directory:
        app = fixture_app(Path(directory), rows)
        with TestClient(app) as client:
            headers = {"Authorization": "Bearer " + app.state.perf_token}

            def request(path):
                response = client.get(path, headers=headers)
                if response.status_code != 200 or response.json().get("success") is not True:
                    raise RuntimeError(f"unexpected status {response.status_code}")
                if "items" in response.json()["data"]:
                    assert response.json()["data"]["total"] == rows
                    assert len(response.json()["data"]["items"]) == min(20, rows)

            http = {
                path: measure(lambda: request(path), samples, concurrency)
                for path in (
                    "/api/v1/health",
                    "/api/v1/evaluations?limit=20",
                    "/api/v1/tasks?limit=20",
                )
            }
            store = ProblemStore(app.state.task_session_factory)

            def lookup():
                assert store.get_by_problem_id(f"perf-{rows // 2:08d}") is not None

            def page():
                assert len(store.list_problems(limit=20, offset=max(0, rows - 20))) == min(20, rows)

            def evaluations():
                items, total = app.state.evaluations.list_evaluations(
                    app.state.perf_owner, limit=20
                )
                assert total == rows and len(items) == min(20, rows)

            db = {
                name: measure(op, samples)
                for name, op in {
                    "problem_lookup": lookup,
                    "problem_deep_page": page,
                    "problem_count": store.count,
                    "owned_evaluations_page": evaluations,
                }.items()
            }
    return {
        "schema": "harness.performance.v1",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "cpu_count": os.cpu_count(),
            **{name: version(name) for name in ("fastapi", "sqlalchemy", "httpx")},
        },
        "configuration": {
            "mode": "in_process_testclient",
            "database": "temporary_file_sqlite",
            "rows_per_table": rows,
            "samples_per_operation": samples,
            "http_concurrency": concurrency,
            "db_concurrency": 1,
            "warmup_per_operation": 3,
        },
        "http": http,
        "database": db,
    }


def failed(report, max_p95_ms=None):
    return any(
        result["errors"] or (max_p95_ms is not None and result["p95_ms"] > max_p95_ms)
        for group in ("http", "database")
        for result in report[group].values()
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=positive, default=1000)
    parser.add_argument("--samples", type=positive, default=100)
    parser.add_argument("--concurrency", type=positive, default=4)
    parser.add_argument("--output", type=Path, default=Path("/tmp/harness-performance.json"))
    parser.add_argument("--max-p95-ms", type=float)
    parser.add_argument(
        "--serve", action="store_true", help="serve a temporary fixture on loopback"
    )
    parser.add_argument("--port", type=positive, default=8099)
    parser.add_argument("--token-file", type=Path, default=Path("/tmp/harness-performance.token"))
    args = parser.parse_args()
    if args.max_p95_ms is not None and (not math.isfinite(args.max_p95_ms) or args.max_p95_ms <= 0):
        parser.error("--max-p95-ms must be finite and positive")
    if args.serve:
        import uvicorn

        with TemporaryDirectory(prefix="harness-load-") as directory:
            uvicorn.run(
                fixture_app(Path(directory), args.rows, args.token_file),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
            )
        return 0
    report = run_benchmark(args.rows, args.samples, args.concurrency)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Benchmark report: {args.output}")
    return int(failed(report, args.max_p95_ms))


if __name__ == "__main__":
    raise SystemExit(main())
