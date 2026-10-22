"""Service for fixed-budget experiment management via the API (issue #156).

Persists experiment configuration (never secrets) in the business database,
submits execution to the Celery experiment task, and reads result
analysis from the experiment artifact directory.
"""

import json
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from threading import Semaphore
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from api.auth.service import AuthService
from api.config import settings
from api.datasets import resolve_dataset_path
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


def _job_view(row: Experiment) -> dict[str, Any]:
    """API-safe view of a job row; internal paths stay server-side."""
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "config": row.config,
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

    def _validate_request(self, request: ExperimentCreateRequest, owner_id: str) -> None:
        """Fail fast on key ownership and dataset placement before persisting."""
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        for spec in request.models:
            self._auth.owned_key(self._key_id_for(request, spec), owner_id)
        resolve_dataset_path(request.dataset_path)

    # -- CRUD ----------------------------------------------------------------

    def create_experiment(self, request: ExperimentCreateRequest, owner_id: str) -> dict[str, Any]:
        """Validate and persist a new experiment configuration."""
        self._validate_request(request, owner_id)
        config: dict[str, Any] = {
            "name": request.name,
            "dataset_path": request.dataset_path,
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
            return _job_view(self._owned(session, experiment_id, owner_id))

    def list_experiments(
        self, owner_id: str, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        with self._session() as session:
            query = select(Experiment).where(Experiment.user_id == owner_id)
            if status:
                query = query.where(Experiment.status == status)
            rows = session.scalars(query.order_by(Experiment.created_at, Experiment.id)).all()
        total = len(rows)
        return [_job_view(row) for row in rows[offset : offset + limit]], total

    def delete_experiment(self, experiment_id: str, owner_id: str) -> None:
        with self._session() as session, session.begin():
            row = self._owned(session, experiment_id, owner_id)
            if row.status == "running":
                raise ValueError("Cannot delete a running experiment; wait for it to finish")
            session.delete(row)

    # -- execution -----------------------------------------------------------

    def start_experiment(self, experiment_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._owned(session, experiment_id, owner_id)
            if row.status != "pending":
                raise ValueError(f"Cannot start experiment in {row.status} status")
            view = _job_view(row)
            task = TaskManager(session).enqueue_task(
                task_type="experiment",
                entity_id=experiment_id,
                user_id=owner_id,
                celery_task_name="src.tasks.experiment.run_experiment_task",
                celery_task_args=(experiment_id, owner_id),
            )
            view["task_id"] = task.id
            return view

    def _build_runner_config(self, row: Experiment, owner_id: str) -> ExperimentConfig:
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        config = row.config
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
            dataset_path=str(resolve_dataset_path(config["dataset_path"])),
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
        with self._concurrent_semaphore:
            try:
                with self._session() as session:
                    row = self._owned(session, experiment_id, owner_id)
                if row.status != "running":
                    return
                config = self._build_runner_config(row, owner_id)
                runner = self._runner_factory(config)
                runner.should_pause = lambda: self._async_task_paused(experiment_id, owner_id)
                runner.on_combination = lambda current, total, model, strategy, repeat: (
                    self._write_progress(
                        experiment_id,
                        owner_id,
                        current,
                        total,
                        f"{model}/{strategy}/{repeat}",
                    )
                )
                exp_dir = runner.run()
                if getattr(runner, "paused", False):
                    with self._session() as session, session.begin():
                        paused = session.get(Experiment, experiment_id, with_for_update=True)
                        if paused is not None and paused.status == "running":
                            paused.status = "paused"
                            paused.updated_at = utcnow()
                    return
                with self._session() as session, session.begin():
                    done = session.get(Experiment, experiment_id, with_for_update=True)
                    if done is None or done.status != "running":
                        return
                    done.status = "completed"
                    done.output_dir = str(exp_dir)
                    done.completed_at = utcnow()
                    done.updated_at = utcnow()
            except Exception as e:  # noqa: BLE001 - reported on the row
                self._fail(experiment_id, str(e))

    def _write_progress(
        self,
        experiment_id: str,
        owner_id: str,
        current: int,
        total: int,
        current_step: str,
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
            task.progress = task_progress(current, total, current_step)

    def _async_task_paused(self, experiment_id: str, owner_id: str) -> bool:
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
            return task is not None and task.status == "paused"

    def _fail(self, experiment_id: str, message: str) -> None:
        with self._session() as session, session.begin():
            row = session.get(Experiment, experiment_id, with_for_update=True)
            if row is None or row.status in (*_TERMINAL_STATUSES, "paused"):
                return
            row.status = "failed"
            row.error_message = message
            row.updated_at = utcnow()

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
