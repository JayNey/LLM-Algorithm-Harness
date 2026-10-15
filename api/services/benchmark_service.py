"""Service for benchmark suite management and learning curve tracking (issue #156)."""

import uuid
from collections.abc import Callable
from datetime import datetime
from threading import Semaphore
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth.service import AuthService
from api.config import settings
from api.datasets import resolve_dataset_path
from api.db import (
    AsyncTask,
    BenchmarkRun,
    BenchmarkSuite,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.engine import business_database_url
from api.db.models import utcnow
from api.experiment_models import (
    BenchmarkRunRequest,
    BenchmarkSuiteCreateRequest,
    BenchmarkSuiteUpdateRequest,
)
from src.benchmark.executor import BenchmarkExecutor
from src.benchmark.suite import BenchmarkSuite as SuiteSpec
from src.models import HarnessConfig
from src.task_manager import TaskManager

_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _suite_obj(row: BenchmarkSuite) -> SuiteSpec:
    return SuiteSpec(
        name=row.name,
        problems=list(row.problems),
        frozen=bool(row.frozen),
        version=row.version,
        description=row.description,
    )


def _suite_view(row: BenchmarkSuite) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "version": row.version,
        "description": row.description,
        "frozen": bool(row.frozen),
        "problems": list(row.problems),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _run_view(row: BenchmarkRun, *, include_results: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "suite_id": row.suite_id,
        "status": row.status,
        "model": row.model,
        "accuracy": row.accuracy,
        "cost_usd": row.cost_usd,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }
    if include_results:
        payload["results"] = row.results if row.results is not None else {}
    return payload


def _trend(values: list[float]) -> float | None:
    """Relative change rate between the first and last observation."""
    if len(values) < 2:
        return None
    first = values[0]
    if first == 0:
        return None
    return round((values[-1] - first) / abs(first), 4)


class BenchmarkService:
    """Manage benchmark suites, runs and learning curves."""

    def __init__(
        self,
        database_url: str | None = None,
        auth: AuthService | None = None,
        executor_factory: Callable[[SuiteSpec, HarnessConfig], Any] = BenchmarkExecutor,
        recover: bool = True,
    ):
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)
        self._auth = auth
        self._executor_factory = executor_factory
        self._concurrent_semaphore = Semaphore(settings.MAX_CONCURRENT_TASKS)
        if recover:
            self._recover_interrupted()

    def _session(self) -> Session:
        return self._session_factory()

    def _recover_interrupted(self) -> None:
        with self._session() as session, session.begin():
            queued = set(
                session.scalars(
                    select(AsyncTask.entity_id).where(
                        AsyncTask.task_type == "benchmark",
                        AsyncTask.status.in_(("pending", "running")),
                    )
                )
            )
            rows = session.scalars(
                select(BenchmarkRun).where(BenchmarkRun.status.in_(("pending", "running")))
            )
            for row in rows:
                if row.status == "pending" and row.id in queued:
                    continue
                row.status = "failed"
                row.error_message = "interrupted by service restart"
                row.updated_at = utcnow()

    def _owned_suite(self, session: Session, suite_id: str, owner_id: str) -> BenchmarkSuite:
        row = session.get(BenchmarkSuite, suite_id)
        if row is None or row.user_id != owner_id:
            raise ValueError(f"Benchmark suite {suite_id} not found")
        return row

    def _owned_run(self, session: Session, run_id: str, owner_id: str) -> BenchmarkRun:
        row = session.get(BenchmarkRun, run_id)
        if row is None or row.user_id != owner_id:
            raise ValueError(f"Benchmark run {run_id} not found")
        return row

    # -- suites --------------------------------------------------------------

    def create_suite(self, request: BenchmarkSuiteCreateRequest, owner_id: str) -> dict[str, Any]:
        row = BenchmarkSuite(
            id=str(uuid.uuid4()),
            user_id=owner_id,
            name=request.name.strip(),
            version=request.version,
            description=request.description,
            frozen=request.frozen,
            problems=list(request.problems),
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self._session() as session, session.begin():
            try:
                session.add(row)
                session.flush()
            except IntegrityError:
                raise ValueError("Benchmark suite name already exists") from None
        return _suite_view(row)

    def list_suites(self, owner_id: str) -> list[dict[str, Any]]:
        with self._session() as session:
            rows = session.scalars(
                select(BenchmarkSuite)
                .where(BenchmarkSuite.user_id == owner_id)
                .order_by(BenchmarkSuite.created_at, BenchmarkSuite.id)
            ).all()
        return [_suite_view(row) for row in rows]

    def get_suite(self, suite_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            return _suite_view(self._owned_suite(session, suite_id, owner_id))

    def update_suite(
        self, suite_id: str, request: BenchmarkSuiteUpdateRequest, owner_id: str
    ) -> dict[str, Any]:
        with self._session() as session, session.begin():
            row = self._owned_suite(session, suite_id, owner_id)
            if row.frozen:
                raise ValueError("Cannot update a frozen benchmark suite")
            if request.problems is not None:
                row.problems = list(request.problems)
            if request.version is not None:
                row.version = request.version
            if request.description is not None:
                row.description = request.description
            if request.frozen is not None:
                row.frozen = request.frozen
            row.updated_at = utcnow()
            return _suite_view(row)

    # -- runs ----------------------------------------------------------------

    def start_run(
        self, suite_id: str, request: BenchmarkRunRequest, owner_id: str
    ) -> dict[str, Any]:
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        self._auth.owned_key(request.api_key_id, owner_id)
        resolve_dataset_path(request.dataset_path)
        with self._session() as session, session.begin():
            suite = self._owned_suite(session, suite_id, owner_id)
            row = BenchmarkRun(
                id=str(uuid.uuid4()),
                suite_id=suite.id,
                user_id=owner_id,
                status="pending",
                model=request.model,
                config={
                    "model": request.model,
                    "dataset_path": request.dataset_path,
                    "strategies": [s.model_dump(mode="json") for s in request.strategies],
                    "budget_cap_usd": request.budget_cap_usd,
                    "problem_filters": request.problem_filters,
                    "api_key_id": request.api_key_id,
                },
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            view = _run_view(row)
            run_id = row.id

        with self._session() as session:
            task = TaskManager(session).enqueue_task(
                task_type="benchmark",
                entity_id=run_id,
                user_id=owner_id,
                celery_task_name="src.tasks.benchmark.run_benchmark_task",
                celery_task_args=(run_id, owner_id),
            )
            view["task_id"] = task.id
            return view

    def _execute(self, run_id: str, owner_id: str) -> None:
        with self._concurrent_semaphore:
            try:
                if self._auth is None:
                    raise ValueError("authentication service is not configured")
                with self._session() as session, session.begin():
                    row = self._owned_run(session, run_id, owner_id)
                    if row.status != "pending":
                        return
                    row.status = "running"
                    row.started_at = utcnow()
                    suite_row = self._owned_suite(session, row.suite_id, owner_id)
                    suite = _suite_obj(suite_row)
                    config_dict = dict(row.config)

                harness_config = HarnessConfig(
                    llm_config=self._auth.llm_config(
                        config_dict["api_key_id"], owner_id, config_dict["model"]
                    ),
                    dataset_path=str(resolve_dataset_path(config_dict["dataset_path"])),
                    strategies=config_dict.get("strategies") or [],
                    budget_cap_usd=config_dict.get("budget_cap_usd"),
                    problem_filters=config_dict.get("problem_filters"),
                )
                results = self._executor_factory(suite, harness_config).execute() or {}

                with self._session() as session, session.begin():
                    done = self._owned_run(session, run_id, owner_id)
                    if done.status != "running":
                        return
                    summary = results.get("summary") if isinstance(results, dict) else None
                    summary = summary if isinstance(summary, dict) else {}
                    done.status = "completed"
                    done.accuracy = (
                        results.get("accuracy") if isinstance(results, dict) else None
                    ) or summary.get("accuracy")
                    done.cost_usd = (
                        results.get("cost_usd") if isinstance(results, dict) else None
                    ) or summary.get("cost_usd")
                    done.results = results if isinstance(results, dict) else {"raw": results}
                    done.completed_at = utcnow()
                    done.updated_at = utcnow()
            except Exception as e:  # noqa: BLE001 - reported on the row
                self._fail(run_id, str(e))

    def _fail(self, run_id: str, message: str) -> None:
        with self._session() as session, session.begin():
            row = session.get(BenchmarkRun, run_id, with_for_update=True)
            if row is None or row.status in _TERMINAL_STATUSES:
                return
            row.status = "failed"
            row.error_message = message
            row.updated_at = utcnow()

    def get_run(self, run_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            return _run_view(self._owned_run(session, run_id, owner_id), include_results=True)

    # -- learning curve ------------------------------------------------------

    def learning_curve(self, suite_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            suite = self._owned_suite(session, suite_id, owner_id)
            rows = session.scalars(
                select(BenchmarkRun)
                .where(
                    BenchmarkRun.suite_id == suite_id,
                    BenchmarkRun.status == "completed",
                )
                .order_by(BenchmarkRun.completed_at, BenchmarkRun.id)
            ).all()

        data = [
            {
                "timestamp": _iso(row.completed_at) if row.completed_at else None,
                "model": row.model,
                "accuracy": row.accuracy,
                "cost_usd": row.cost_usd,
            }
            for row in rows
        ]
        accuracies = [float(p["accuracy"]) for p in data if p["accuracy"] is not None]
        costs = [float(p["cost_usd"]) for p in data if p["cost_usd"] is not None]
        return {
            "suite_id": suite.id,
            "suite_name": suite.name,
            "data": data,
            "trends": {
                "accuracy_growth_rate": _trend(accuracies),
                "cost_growth_rate": _trend(costs),
            },
        }
