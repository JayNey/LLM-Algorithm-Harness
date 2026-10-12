"""Service for A/B prompt testing via the API (issue #156)."""

import json
import threading
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
from api.db import ABTest, make_engine, make_session_factory, run_migrations
from api.db.engine import business_database_url
from api.db.models import utcnow
from api.experiment_models import ABTestCreateRequest, ModelSpec
from src.ab_testing import ABTestConfig, ABTestRunner

_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _job_view(row: ABTest) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "status": row.status,
        "config": row.config,
        "error_message": row.error_message,
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


class ABTestService:
    """Create, run and report A/B prompt tests."""

    def __init__(
        self,
        database_url: str | None = None,
        auth: AuthService | None = None,
        runner_factory: Callable[[ABTestConfig], Any] = ABTestRunner,
    ):
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)
        self._auth = auth
        self._runner_factory = runner_factory
        self._concurrent_semaphore = Semaphore(settings.MAX_CONCURRENT_TASKS)
        self._recover_interrupted()

    def _session(self) -> Session:
        return self._session_factory()

    def _recover_interrupted(self) -> None:
        with self._session() as session, session.begin():
            rows = session.scalars(select(ABTest).where(ABTest.status.in_(("pending", "running"))))
            for row in rows:
                row.status = "failed"
                row.error_message = "interrupted by service restart"
                row.updated_at = utcnow()

    def _owned(self, session: Session, test_id: str, owner_id: str) -> ABTest:
        row = session.get(ABTest, test_id)
        if row is None or row.user_id != owner_id:
            raise ValueError(f"A/B test {test_id} not found")
        return row

    # -- CRUD ----------------------------------------------------------------

    def create_test(self, request: ABTestCreateRequest, owner_id: str) -> dict[str, Any]:
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        self._auth.owned_key(request.api_key_id, owner_id)
        resolve_dataset_path(request.dataset_path)
        ids = [variant.id for variant in request.prompt_variants]
        if len(set(ids)) != len(ids):
            raise ValueError("prompt_variants must contain unique IDs")
        config: dict[str, Any] = {
            "name": request.name,
            "dataset_path": request.dataset_path,
            "model": {
                "model": request.model.model,
                "base_url": request.model.base_url,
                "temperature": request.model.temperature,
            },
            "strategy": request.strategy.model_dump(mode="json"),
            "prompt_variants": [v.model_dump(mode="json") for v in request.prompt_variants],
            "baseline_id": request.baseline_id,
            "seed": request.seed,
            "max_workers": request.max_workers,
            "problem_filters": request.problem_filters,
            "api_key_id": request.api_key_id,
        }
        row = ABTest(
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

    def get_test(self, test_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            return _job_view(self._owned(session, test_id, owner_id))

    def list_tests(
        self, owner_id: str, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[dict[str, Any]], int]:
        with self._session() as session:
            query = select(ABTest).where(ABTest.user_id == owner_id)
            if status:
                query = query.where(ABTest.status == status)
            rows = session.scalars(query.order_by(ABTest.created_at, ABTest.id)).all()
        total = len(rows)
        return [_job_view(row) for row in rows[offset : offset + limit]], total

    def delete_test(self, test_id: str, owner_id: str) -> None:
        with self._session() as session, session.begin():
            row = self._owned(session, test_id, owner_id)
            if row.status == "running":
                raise ValueError("Cannot delete a running A/B test; cancel it first")
            session.delete(row)

    # -- execution -----------------------------------------------------------

    def start_test(self, test_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session, session.begin():
            row = self._owned(session, test_id, owner_id)
            if row.status != "pending":
                raise ValueError(f"Cannot start A/B test in {row.status} status")
            row.status = "running"
            row.started_at = utcnow()
            row.updated_at = utcnow()
            view = _job_view(row)

        thread = threading.Thread(target=self._execute, args=(test_id, owner_id), daemon=True)
        thread.start()
        return view

    def _build_config(self, row: ABTest, owner_id: str) -> ABTestConfig:
        if self._auth is None:
            raise ValueError("authentication service is not configured")
        config = row.config
        spec = ModelSpec(**config["model"])
        llm = self._auth.llm_config(row.api_key_id or "", owner_id, spec.model)
        update: dict[str, Any] = {}
        if spec.base_url:
            update["base_url"] = spec.base_url
        if spec.temperature is not None:
            update["temperature"] = spec.temperature
        if update:
            llm = llm.model_copy(update=update)
        return ABTestConfig(
            name=config["name"] or f"api-{row.id[:8]}",
            dataset_path=str(resolve_dataset_path(config["dataset_path"])),
            output_dir=f"results/ab-tests/api/{row.id}",
            model=llm,
            strategy=config["strategy"],
            prompt_variants=config["prompt_variants"],
            baseline_id=config["baseline_id"],
            seed=config["seed"],
            max_workers=config["max_workers"],
            problem_filters=config["problem_filters"],
        )

    def _execute(self, test_id: str, owner_id: str) -> None:
        with self._concurrent_semaphore:
            try:
                with self._session() as session:
                    row = self._owned(session, test_id, owner_id)
                if row.status != "running":
                    return
                config = self._build_config(row, owner_id)
                output_dir = self._runner_factory(config).run()
                with self._session() as session, session.begin():
                    done = self._owned(session, test_id, owner_id)
                    if done.status != "running":
                        return
                    done.status = "completed"
                    done.output_dir = str(output_dir)
                    done.completed_at = utcnow()
                    done.updated_at = utcnow()
            except Exception as e:  # noqa: BLE001 - reported on the row
                self._fail(test_id, str(e))

    def _fail(self, test_id: str, message: str) -> None:
        with self._session() as session, session.begin():
            row = session.get(ABTest, test_id, with_for_update=True)
            if row is None or row.status in _TERMINAL_STATUSES:
                return
            row.status = "failed"
            row.error_message = message
            row.updated_at = utcnow()

    # -- results -------------------------------------------------------------

    def results(self, test_id: str, owner_id: str) -> dict[str, Any]:
        with self._session() as session:
            row = self._owned(session, test_id, owner_id)
            if row.status != "completed" or not row.output_dir:
                raise ValueError(f"A/B test {test_id} has no results yet (status: {row.status})")
            report = Path(row.output_dir) / "ab_test.json"
            if not report.is_file():
                raise ValueError(f"A/B test {test_id} artifacts are missing")
            payload = json.loads(report.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {"results": payload}
