"""Service for fixed-budget experiment management via the API (issue #156).

Persists experiment configuration (never secrets) in the business database,
submits execution to the Celery experiment task, and reads result
analysis from the experiment artifact directory.
"""

import json
import uuid
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from threading import Semaphore
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.orm import Session

from api.auth.service import AuthService
from api.config import settings
from api.datasets import (
    execution_dataset,
    freeze_dataset,
    public_dataset_config,
    resolve_dataset_path,
)
from api.db import AsyncTask, Experiment, make_engine, make_session_factory, run_migrations
from api.db.engine import business_database_url
from api.db.models import utcnow
from api.experiment_models import ExperimentCreateRequest, ModelSpec
from src.experiment import ExperimentRunner
from src.experiment_panel import _build_panel_data
from src.experiment_report import generate_comparison_report
from src.models import ExperimentConfig
from src.task_manager import TaskManager
from src.tasks.support import task_progress

_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _job_view(row: Experiment, task_id: str | None = None) -> dict[str, Any]:
    """API-safe view of a job row; internal paths stay server-side."""
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "task_id": task_id,
        "config": public_dataset_config(row.config),
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class ExperimentService:
    """Create, run and analyze fixed-budget experiments."""

    def __init__(
        self,
        database_url: str | None = None,
        auth: AuthService | None = None,
        runner_factory: Callable[[ExperimentConfig], Any] = ExperimentRunner,
        recover: bool = True,
    ):
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)
        self._auth = auth
        self._runner_factory = runner_factory
        self._concurrent_semaphore = Semaphore(settings.MAX_CONCURRENT_TASKS)
        if recover:
            self._recover_interrupted()

    # -- persistence helpers -------------------------------------------------

    def _session(self) -> Session:
        return self._session_factory()

    def _recover_interrupted(self) -> None:
        """Preserve queued and running records owned by independent workers."""
        with self._session() as session, session.begin():
            live_tasks = set(
                session.scalars(
                    select(AsyncTask.entity_id).where(
                        AsyncTask.task_type == "experiment",
                        AsyncTask.status.in_(("pending", "running", "paused")),
                    )
                )
            )
            rows = session.scalars(
                select(Experiment).where(Experiment.status.in_(("pending", "running")))
            )
            for row in rows:
                if row.id in live_tasks:
                    continue
                row.status = "failed"
                row.error_message = "interrupted by service restart"
                row.updated_at = utcnow()

    def _owned(self, session: Session, experiment_id: str, owner_id: str) -> Experiment:
        row = session.get(Experiment, experiment_id)
        if row is None or row.user_id != owner_id:
            raise ValueError(f"Experiment {experiment_id} not found")
        return row

    def _key_id_for(self, request: ExperimentCreateRequest, spec: ModelSpec) -> str:
        return spec.api_key_id or request.api_key_id

    def _validate_request(self, request: ExperimentCreateRequest, owner_id: str) -> AuthService:
        """Fail fast on key ownership and dataset placement before persisting."""
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        for spec in request.models:
            self._auth.owned_key(self._key_id_for(request, spec), owner_id)
        return self._auth

    # -- CRUD ----------------------------------------------------------------

    def create_experiment(self, request: ExperimentCreateRequest, owner_id: str) -> dict[str, Any]:
        """Validate and persist a new experiment configuration."""
        auth = self._validate_request(request, owner_id)
        config: dict[str, Any] = {
            "name": request.name,
            "dataset_path": request.dataset_path,
            "dataset_id": request.dataset_id,
            "dataset_snapshot": freeze_dataset(
                request.dataset_id, request.dataset_path, owner_id, auth
            ),
            "models": [
                {
                    "model": spec.model,
                    "base_url": spec.base_url,
                    "temperature": spec.temperature,
                    "api_key_id": self._key_id_for(request, spec),
                }
                for spec in request.models
            ],
            "strategies": [s.model_dump(mode="json") for s in request.strategies],
            "repeats": request.repeats,
            "budget": request.budget.model_dump(mode="json") if request.budget else None,
            "execution": request.execution,
            "max_workers": request.max_workers,
            "problem_filters": request.problem_filters,
        }
        row = Experiment(
            id=str(uuid.uuid4()),
            user_id=owner_id,
            name=request.name,
            status="pending",
            config=config,
            api_key_id=request.api_key_id,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self._session() as session, session.begin():
            session.add(row)
        return _job_view(row)

    def get_experiment(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._owned(session, experiment_id, owner_id)
            task = self._task(session, experiment_id, owner_id)
            return _job_view(row, task.id if task else None)

    @staticmethod
    def _task(
        session: Session, experiment_id: str, owner_id: str, *, active_only: bool = False
    ) -> AsyncTask | None:
        query = (
            select(AsyncTask)
            .where(
                AsyncTask.task_type == "experiment",
                AsyncTask.entity_id == experiment_id,
                AsyncTask.user_id == owner_id,
            )
            .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
        )
        if active_only:
            query = query.where(AsyncTask.status.in_(("pending", "running", "paused")))
        return session.scalar(query)

    @staticmethod
    def _lock_experiment(session: Session, experiment_id: str, owner_id: str) -> None:
        # Acquire a database write lock BEFORE reading, including on SQLite.
        # Submission and deletion must share this lock across API processes.
        session.execute(
            update(Experiment)
            .where(Experiment.id == experiment_id, Experiment.user_id == owner_id)
            .values(id=Experiment.id, updated_at=Experiment.updated_at)
            .execution_options(synchronize_session=False)
        )

    def list_experiments(
        self, owner_id: str, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        with self._session() as session:
            query = select(Experiment).where(Experiment.user_id == owner_id)
            if status:
                query = query.where(Experiment.status == status)
            rows = session.scalars(query.order_by(Experiment.created_at, Experiment.id)).all()
            total = len(rows)
            page = rows[offset : offset + limit]
            task_ids: dict[str, str] = {}
            if page:
                tasks = session.scalars(
                    select(AsyncTask)
                    .where(
                        AsyncTask.task_type == "experiment",
                        AsyncTask.user_id == owner_id,
                        AsyncTask.entity_id.in_([row.id for row in page]),
                    )
                    .order_by(AsyncTask.created_at.desc(), AsyncTask.id.desc())
                )
                for task in tasks:
                    task_ids.setdefault(task.entity_id, task.id)
            return [_job_view(row, task_ids.get(row.id)) for row in page], total

    def delete_experiment(self, experiment_id: str, owner_id: str) -> None:
        with self._session() as session, session.begin():
            self._lock_experiment(session, experiment_id, owner_id)
            row = self._owned(session, experiment_id, owner_id)
            active_task = self._task(session, experiment_id, owner_id, active_only=True)
            if row.status == "running":
                raise ValueError("Cannot delete a running experiment; wait for it to finish")
            if row.status == "paused" or active_task is not None:
                raise ValueError(
                    "Cannot delete an active experiment; cancel it or wait for it to finish"
                )
            session.delete(row)

    # -- execution -----------------------------------------------------------

    def start_experiment(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            self._lock_experiment(session, experiment_id, owner_id)
            row = self._owned(session, experiment_id, owner_id)
            if row.status != "pending":
                raise ValueError(f"Cannot start experiment in {row.status} status")
            if self._task(session, experiment_id, owner_id) is not None:
                raise ValueError("Cannot start experiment: already queued")
            task = TaskManager(session).enqueue_task(
                task_type="experiment",
                entity_id=experiment_id,
                user_id=owner_id,
                celery_task_name="src.tasks.experiment.run_experiment_task",
                celery_task_args=(experiment_id, owner_id),
            )
            session.refresh(row)
            return _job_view(row, task.id)

    def _build_runner_config(
        self, row: Experiment, owner_id: str, dataset_files: ExitStack | None = None
    ) -> ExperimentConfig:
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        config = row.config
        if config.get("dataset_snapshot") is not None or config.get("dataset_id"):
            if dataset_files is None:
                raise ValueError("Dataset snapshot requires an execution scope")
            dataset_path = dataset_files.enter_context(execution_dataset(config, owner_id))
        else:
            dataset_path = str(resolve_dataset_path(config["dataset_path"]))
        models: list[Any] = []
        for spec in config["models"]:
            llm = self._auth.llm_config(spec["api_key_id"], owner_id, spec["model"])
            update: dict[str, Any] = {}
            if spec.get("base_url"):
                update["base_url"] = spec["base_url"]
            if spec.get("temperature") is not None:
                update["temperature"] = spec["temperature"]
            models.append(llm.model_copy(update=update) if update else llm)
        return ExperimentConfig(
            name=config["name"] or f"api-{row.id[:8]}",
            dataset_path=dataset_path,
            output_dir=f"results/experiments/api/{row.id}",
            models=models,
            strategies=config["strategies"],
            repeats=config["repeats"],
            budget=config["budget"],
            execution=config["execution"],
            max_workers=config["max_workers"],
            problem_filters=config["problem_filters"],
        )

    def _execute(self, experiment_id: str, owner_id: str) -> None:
        generation = None
        with self._concurrent_semaphore, ExitStack() as dataset_files:
            try:
                with self._session() as session:
                    row = self._owned(session, experiment_id, owner_id)
                    task = self._task(session, experiment_id, owner_id)
                    generation = task.celery_task_id if task is not None else None
                if row.status != "running":
                    return
                config = self._build_runner_config(row, owner_id, dataset_files)
                runner = self._runner_factory(config)
                from api.services.spend_records import SpendRecorder, pricing_snapshot

                recorder = SpendRecorder(self._session, "experiments", experiment_id, owner_id)
                runner.pricing_manager = pricing_snapshot(self._session)
                runner.on_spend = lambda eid, response, cached, context: recorder.callback(
                    **context
                )(eid, response, cached)
                runner.before_generate = recorder.check
                runner.checkpoint_dir = Path(f"results/experiments/api/{experiment_id}/execution")
                runner.should_pause = lambda: self._async_task_stopped(
                    experiment_id, owner_id, generation
                )
                runner.on_combination = lambda current, total, model, strategy, repeat: (
                    self._write_progress(
                        experiment_id,
                        owner_id,
                        current,
                        total,
                        f"{model}/{strategy}/{repeat}",
                        generation,
                    )
                )
                exp_dir = runner.run()
                recorder.check()
                if getattr(runner, "paused", False):
                    self._finish(experiment_id, owner_id, "paused", celery_task_id=generation)
                    return
                self._finish(
                    experiment_id,
                    owner_id,
                    "completed",
                    output_dir=str(exp_dir),
                    celery_task_id=generation,
                )
            except Exception as e:  # noqa: BLE001 - reported on the row
                self._finish(
                    experiment_id,
                    owner_id,
                    "failed",
                    error_message=str(e),
                    celery_task_id=generation,
                )

    def _finish(
        self,
        experiment_id: str,
        owner_id: str,
        status: str,
        *,
        output_dir: str | None = None,
        error_message: str | None = None,
        celery_task_id: str | None = None,
    ) -> None:
        """Commit the result and task together, after any competing cancellation."""
        with self._session() as session:
            task = session.scalar(
                select(AsyncTask).where(
                    AsyncTask.task_type == "experiment",
                    AsyncTask.entity_id == experiment_id,
                    AsyncTask.user_id == owner_id,
                )
            )
            manager = TaskManager(session, celery_task_id=celery_task_id)
            if task is not None:
                manager._lock_business_task(task)
                if celery_task_id is not None and task.celery_task_id != celery_task_id:
                    return
                if task.status in _TERMINAL_STATUSES:
                    return
                if task.status == "paused":
                    status = "paused"
            values: dict[str, Any] = {"status": status, "updated_at": utcnow()}
            if status in _TERMINAL_STATUSES:
                values["completed_at"] = utcnow()
                values["error_message"] = error_message
            if status == "completed":
                values["output_dir"] = output_dir
            changed = session.execute(
                update(Experiment)
                .where(
                    Experiment.id == experiment_id,
                    Experiment.user_id == owner_id,
                    Experiment.status == "running",
                )
                .values(**values)
            )
            if not cast(CursorResult[Any], changed).rowcount:
                return
            if task is not None:
                manager.update_task_status(task.id, status, error_message=error_message)
            else:
                session.commit()

    def _write_progress(
        self,
        experiment_id: str,
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
                    AsyncTask.task_type == "experiment",
                    AsyncTask.entity_id == experiment_id,
                    AsyncTask.user_id == owner_id,
                )
                .first()
            )
            if task is None or task.status != "running":
                return
            TaskManager(session, celery_task_id=celery_task_id).update_task_progress(
                task.id, task_progress(current, total, current_step), "running"
            )

    def _async_task_stopped(
        self, experiment_id: str, owner_id: str, celery_task_id: str | None = None
    ) -> bool:
        with self._session() as session:
            task = (
                session.query(AsyncTask)
                .populate_existing()
                .filter(
                    AsyncTask.task_type == "experiment",
                    AsyncTask.entity_id == experiment_id,
                    AsyncTask.user_id == owner_id,
                )
                .first()
            )
            return task is not None and (
                task.status != "running"
                or (celery_task_id is not None and task.celery_task_id != celery_task_id)
            )

    # -- results -------------------------------------------------------------

    def _completed_output_dir(self, session: Session, experiment_id: str, owner_id: str) -> Path:
        row = self._owned(session, experiment_id, owner_id)
        if row.status != "completed" or not row.output_dir:
            raise ValueError(
                f"Experiment {experiment_id} has no results yet (status: {row.status})"
            )
        exp_dir = Path(row.output_dir)
        if not exp_dir.is_dir():
            raise ValueError(f"Experiment {experiment_id} artifacts are missing")
        return exp_dir

    def results(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            exp_dir = self._completed_output_dir(session, experiment_id, owner_id)
            meta = exp_dir / "experiment.json"
            if not meta.is_file():
                raise ValueError(f"Experiment {experiment_id} artifacts are missing")
            payload = json.loads(meta.read_text(encoding="utf-8"))
        combos = [
            {
                "model": combo.get("model"),
                "strategy": combo.get("strategy"),
                "repeat": combo.get("repeat"),
                "status": combo.get("status"),
            }
            for combo in payload.get("combinations", [])
        ]
        return {
            "experiment_id": payload.get("experiment_id"),
            "name": payload.get("name"),
            "status": "completed",
            "created_at": payload.get("created_at"),
            "finished_at": payload.get("finished_at"),
            "models": [m.get("model") for m in payload.get("models", [])],
            "strategies": payload.get("strategies", []),
            "combinations": combos,
        }

    def comparison(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            exp_dir = self._completed_output_dir(session, experiment_id, owner_id)
        try:
            return generate_comparison_report(exp_dir)
        except FileNotFoundError as exc:
            raise ValueError(f"Experiment {experiment_id} artifacts are missing") from exc

    def panel(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        comparison = self.comparison(experiment_id, owner_id)
        return _build_panel_data(comparison)
