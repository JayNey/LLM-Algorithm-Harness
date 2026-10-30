"""Service for benchmark suite management and learning curve tracking (issue #156)."""

import uuid
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from threading import Semaphore
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from api.auth.service import AuthService
from api.config import settings
from api.datasets import execution_dataset, freeze_dataset, resolve_dataset_path, snapshot_summary
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
from src.tasks.support import task_progress

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


def _run_view(
    row: BenchmarkRun, *, task_id: str | None = None, include_results: bool = False
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": row.id,
        "suite_id": row.suite_id,
        "task_id": task_id,
        "status": row.status,
        "model": row.model,
        "dataset_snapshot": snapshot_summary(row.config),
        "accuracy": row.accuracy,
        "cost_usd": row.cost_usd,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "started_at": _iso(row.started_at) if row.started_at else None,
        "completed_at": _iso(row.completed_at) if row.completed_at else None,
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
        """Preserve queued and running records owned by independent workers."""
        with self._session() as session, session.begin():
            live_tasks = set(
                session.scalars(
                    select(AsyncTask.entity_id).where(
                        AsyncTask.task_type == "benchmark",
                        AsyncTask.status.in_(("pending", "running", "paused")),
                    )
                )
            )
            rows = session.scalars(
                select(BenchmarkRun).where(BenchmarkRun.status.in_(("pending", "running")))
            )
            for row in rows:
                if row.id in live_tasks:
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
                    "dataset_id": request.dataset_id,
                    "dataset_snapshot": freeze_dataset(
                        request.dataset_id, request.dataset_path, owner_id, self._auth
                    ),
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
        generation = None
        with self._concurrent_semaphore, ExitStack() as dataset_files:
            try:
                if self._auth is None:
                    raise ValueError("authentication service is not configured")
                with self._session() as session:
                    row = self._owned_run(session, run_id, owner_id)
                    task = session.scalar(
                        select(AsyncTask).where(
                            AsyncTask.task_type == "benchmark",
                            AsyncTask.entity_id == run_id,
                            AsyncTask.user_id == owner_id,
                        )
                    )
                    if task is not None:
                        manager = TaskManager(session)
                        manager._lock_business_task(task)
                        if task.status == "pending":
                            manager.claim_task(task.id, task.celery_task_id)
                        generation = task.celery_task_id
                        if task.status != "running":
                            return
                    if row.status not in ("pending", "running"):
                        return
                    row.status = "running"
                    row.started_at = row.started_at or utcnow()
                    suite_row = self._owned_suite(session, row.suite_id, owner_id)
                    suite = _suite_obj(suite_row)
                    config_dict = dict(row.config)
                    session.commit()

                dataset_path = (
                    dataset_files.enter_context(execution_dataset(config_dict, owner_id))
                    if config_dict.get("dataset_snapshot") is not None
                    or config_dict.get("dataset_id")
                    else str(resolve_dataset_path(config_dict["dataset_path"]))
                )
                harness_config = HarnessConfig(
                    llm_config=self._auth.llm_config(
                        config_dict["api_key_id"], owner_id, config_dict["model"]
                    ),
                    dataset_path=dataset_path,
                    strategies=config_dict.get("strategies") or [],
                    budget_cap_usd=config_dict.get("budget_cap_usd"),
                    problem_filters=config_dict.get("problem_filters"),
                )
                from api.services.cost_alert_service import WebCostAlertDispatcher
                from src.tasks.budget_guard import BudgetGuard

                executor = self._executor_factory(suite, harness_config)
                executor.checkpoint_dir = Path("results/benchmarks/api") / run_id / "units"
                budget = BudgetGuard(self._session, owner_id)
                cost_alerts = WebCostAlertDispatcher(self._session, run_id)
                executor.should_pause = (
                    lambda: self._async_task_paused(run_id, owner_id, generation)
                    or budget.should_pause()
                )
                cost_alerts.process(owner_id)

                def on_problem(current: int, total: int, strategy: str, problem_id: str) -> None:
                    self._write_progress(
                        run_id,
                        owner_id,
                        current,
                        total,
                        f"{strategy}/{problem_id}",
                        generation,
                    )
                    cost_alerts.process(owner_id)

                executor.on_problem = on_problem
                results = executor.execute() or {}
                if getattr(executor, "paused", False):
                    # 先锁 AsyncTask 再锁 run，与 TaskManager.cancel_task 的加锁顺序
                    # 一致，避免用户取消与预算暂停在 PostgreSQL 上 AB-BA 死锁。
                    with self._session() as session, session.begin():
                        task_row = session.scalars(
                            select(AsyncTask)
                            .where(
                                AsyncTask.task_type == "benchmark",
                                AsyncTask.entity_id == run_id,
                                AsyncTask.status == "running",
                            )
                            .with_for_update()
                        ).first()
                        if task_row is not None:
                            task_row.status = "paused"
                            task_row.updated_at = utcnow()
                        paused = session.get(BenchmarkRun, run_id, with_for_update=True)
                        if paused is not None and paused.status == "running":
                            paused.status = "paused"
                            paused.updated_at = utcnow()
                    return

                with self._session() as session, session.begin():
                    task = session.scalar(
                        select(AsyncTask).where(
                            AsyncTask.task_type == "benchmark",
                            AsyncTask.entity_id == run_id,
                            AsyncTask.user_id == owner_id,
                        )
                    )
                    if task is not None:
                        TaskManager(session)._lock_business_task(task)
                        if task.status != "running" or task.celery_task_id != generation:
                            return
                    done = self._owned_run(session, run_id, owner_id)
                    if done.status != "running":
                        return
                    summary = results.get("summary") if isinstance(results, dict) else None
                    summary = summary if isinstance(summary, dict) else {}
                    done.status = "completed"
                    done.accuracy = results.get("accuracy") if isinstance(results, dict) else None
                    if done.accuracy is None:
                        done.accuracy = summary.get("accuracy")
                    done.cost_usd = results.get("cost_usd") if isinstance(results, dict) else None
                    if done.cost_usd is None:
                        done.cost_usd = summary.get("cost_usd")
                    done.results = results if isinstance(results, dict) else {"raw": results}
                    done.completed_at = utcnow()
                    done.updated_at = utcnow()
                    if task is not None:
                        TaskManager(session, celery_task_id=generation).update_task_status(
                            task.id, "completed"
                        )
            except Exception as e:  # noqa: BLE001 - reported on the row
                self._fail(run_id, str(e), generation)

    def _write_progress(
        self,
        run_id: str,
        owner_id: str,
        current: int,
        total: int,
        current_step: str,
        celery_task_id: str | None = None,
    ) -> None:
        with self._session() as session, session.begin():
            task = (
                session.query(AsyncTask)
                .filter(
                    AsyncTask.task_type == "benchmark",
                    AsyncTask.entity_id == run_id,
                    AsyncTask.user_id == owner_id,
                )
                .first()
            )
            if task is None or task.status != "running":
                return
            TaskManager(session, celery_task_id=celery_task_id).update_task_progress(
                task.id, task_progress(current, total, current_step), "running"
            )

    def _async_task_paused(
        self, run_id: str, owner_id: str, celery_task_id: str | None = None
    ) -> bool:
        with self._session() as session:
            task = (
                session.query(AsyncTask)
                .populate_existing()
                .filter(
                    AsyncTask.task_type == "benchmark",
                    AsyncTask.entity_id == run_id,
                    AsyncTask.user_id == owner_id,
                )
                .first()
            )
            return task is not None and (
                task.status != "running"
                or (celery_task_id is not None and task.celery_task_id != celery_task_id)
            )

    def _fail(self, run_id: str, message: str, celery_task_id: str | None = None) -> None:
        with self._session() as session, session.begin():
            task = session.scalar(
                select(AsyncTask).where(
                    AsyncTask.task_type == "benchmark", AsyncTask.entity_id == run_id
                )
            )
            if task is not None:
                manager = TaskManager(session, celery_task_id=celery_task_id)
                manager._lock_business_task(task)
                if task.status != "running" or (
                    celery_task_id is not None and task.celery_task_id != celery_task_id
                ):
                    return
                manager.update_task_status(task.id, "failed", error_message=message)
                return
            row = session.get(BenchmarkRun, run_id, with_for_update=True)
            if row is None or row.status in (*_TERMINAL_STATUSES, "paused"):
                return
            row.status = "failed"
            row.error_message = message
            row.updated_at = utcnow()

    @staticmethod
    def _run_task_ids(session: Session, run_ids: list[str], owner_id: str) -> dict[str, str]:
        if not run_ids:
            return {}
        tasks = session.scalars(
            select(AsyncTask)
            .where(
                AsyncTask.task_type == "benchmark",
                AsyncTask.user_id == owner_id,
                AsyncTask.entity_id.in_(run_ids),
            )
            .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
        )
        task_ids: dict[str, str] = {}
        for task in tasks:
            task_ids.setdefault(task.entity_id, task.id)
        return task_ids

    def list_runs(
        self,
        suite_id: str,
        owner_id: str,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        with self._session() as session:
            self._owned_suite(session, suite_id, owner_id)
            query = select(BenchmarkRun).where(
                BenchmarkRun.suite_id == suite_id, BenchmarkRun.user_id == owner_id
            )
            if status is not None:
                query = query.where(BenchmarkRun.status == status)
            total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
            if offset >= total:
                return [], total
            rows = session.scalars(
                query.order_by(BenchmarkRun.created_at.desc(), BenchmarkRun.id.desc())
                .limit(limit)
                .offset(offset)
            ).all()
            task_ids = self._run_task_ids(session, [row.id for row in rows], owner_id)
            return [_run_view(row, task_id=task_ids.get(row.id)) for row in rows], total

    def get_run(self, run_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._owned_run(session, run_id, owner_id)
            self._owned_suite(session, row.suite_id, owner_id)
            task_ids = self._run_task_ids(session, [run_id], owner_id)
            return _run_view(row, task_id=task_ids.get(run_id), include_results=True)

    # -- learning curve ------------------------------------------------------

    def learning_curve(self, suite_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            suite = self._owned_suite(session, suite_id, owner_id)
            rows = session.scalars(
                select(BenchmarkRun)
                .where(
                    BenchmarkRun.suite_id == suite_id,
                    BenchmarkRun.user_id == owner_id,
                    BenchmarkRun.status == "completed",
                )
                .order_by(BenchmarkRun.completed_at, BenchmarkRun.id)
            ).all()

        data = [
            {
                "run_id": row.id,
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
