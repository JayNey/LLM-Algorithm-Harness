"""Service layer for evaluation task management.

Tasks are persisted in the business database (issue #151): creating a task
inserts a row, every status/progress transition is written back, and state
survives restarts. Non-terminal tasks found at startup are marked failed so
#149's task queue can take over scheduling later. The public interface and
transitions match the original in-memory implementation.

Enhanced with async task support (Task 5): create_evaluation now submits Celery
tasks via TaskManager, and get_evaluation aggregates status from AsyncTask.
"""

import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from threading import Semaphore

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from api.config import settings
from api.db import Evaluation, make_engine, make_session_factory, run_migrations
from api.db.engine import business_database_url
from api.db.models import AsyncTask, utcnow
from api.models import EvaluationCreateRequest, EvaluationUpdateRequest
from api.schemas import EvaluationResponse, ProgressInfo
from src.task_manager import TaskManager

INTERRUPTED_BY_RESTART = "interrupted by service restart"
_TERMINAL_STATUSES = ("completed", "failed", "cancelled")


def _iso(value: datetime) -> str:
    return value.isoformat() + "Z"


def _to_response(task: Evaluation) -> EvaluationResponse:
    """Convert an evaluation row to the API response shape.

    Used for legacy in-memory task execution. For async tasks, use _to_response_async.
    """
    percentage = (task.completed_count / task.problem_count * 100) if task.problem_count else 0
    return EvaluationResponse(
        evaluation_id=task.id,
        created_at=_iso(task.created_at),
        updated_at=_iso(task.updated_at),
        status=task.status,
        strategy_names=list(task.strategy_names),
        problem_count=task.problem_count,
        spent_usd=task.spent_usd,
        budget_cap_usd=task.budget_cap_usd,
        error_message=task.error_message,
        progress=ProgressInfo(
            current=task.completed_count,
            total=task.problem_count,
            message=None,
            # Backwards compat
            completed=task.completed_count,
            percentage=percentage,
        ),
    )


def _to_response_async(evaluation: Evaluation, async_task: AsyncTask | None) -> EvaluationResponse:
    """Convert Evaluation and AsyncTask to response, aggregating status.

    Used when evaluation has an associated async task. Aggregates:
    - Status from AsyncTask if it's pending/running, else from Evaluation
    - Progress from AsyncTask if available
    - Error message from AsyncTask if available
    """
    status = evaluation.status
    progress = None
    error_message = evaluation.error_message

    if async_task:
        # Use async task status if it's in non-terminal state
        if async_task.status in ("pending", "running", "paused"):
            status = async_task.status

        # Include progress from async task
        if async_task.progress:
            try:
                progress = ProgressInfo(**async_task.progress)
            except Exception:
                # Fallback if progress dict doesn't match schema
                progress = None

        # Prefer async task error message
        if async_task.error_message:
            error_message = async_task.error_message

    # Compute percentage for backwards compatibility
    percentage = (
        (evaluation.completed_count / evaluation.problem_count * 100)
        if evaluation.problem_count
        else 0
    )

    return EvaluationResponse(
        evaluation_id=evaluation.id,
        created_at=_iso(evaluation.created_at),
        updated_at=_iso(evaluation.updated_at),
        status=status,
        strategy_names=list(evaluation.strategy_names),
        problem_count=evaluation.problem_count,
        spent_usd=evaluation.spent_usd,
        budget_cap_usd=evaluation.budget_cap_usd,
        error_message=error_message,
        progress=progress
        or ProgressInfo(
            current=evaluation.completed_count,
            total=evaluation.problem_count,
            message=None,
            # Backwards compat
            completed=evaluation.completed_count,
            percentage=percentage,
        ),
    )


class EvaluationService:
    """Service for managing evaluation tasks."""

    def __init__(self, database_url: str | None = None):
        """Initialize the service against the business database.

        Runs pending migrations and flags tasks left non-terminal by a
        previous process as failed, so recovery is observable via the API.
        """
        self._engine = make_engine(database_url or business_database_url())
        run_migrations(self._engine)
        self._session_factory = make_session_factory(self._engine)
        self._concurrent_semaphore = Semaphore(settings.MAX_CONCURRENT_TASKS)
        self._recover_interrupted()

    # -- persistence helpers -------------------------------------------------

    @property
    def engine(self) -> Engine:
        """The running service's database engine, available to read-only monitors."""
        return self._engine

    def _session(self) -> Session:
        return self._session_factory()

    def _recover_interrupted(self) -> None:
        with self._session() as session, session.begin():
            interrupted = session.scalars(
                select(Evaluation).where(Evaluation.status.in_(("pending", "running")))
            )
            for task in interrupted:
                task.status = "failed"
                task.error_message = INTERRUPTED_BY_RESTART
                task.updated_at = utcnow()

    def _owned_task(self, session: Session, evaluation_id: str, owner_id: str) -> Evaluation:
        """Load the task owned by ``owner_id`` or raise the 404-mapped error."""
        task = session.get(Evaluation, evaluation_id)
        if task is None or task.user_id != owner_id:
            raise ValueError(f"Evaluation {evaluation_id} not found")
        return task

    # -- CRUD ----------------------------------------------------------------

    def create_evaluation(
        self, request: EvaluationCreateRequest, owner_id: str
    ) -> EvaluationResponse:
        """Create a new evaluation task."""
        task = Evaluation(
            id=str(uuid.uuid4()),
            user_id=owner_id,
            status="pending",
            strategy_names=list(request.strategy_names),
            problem_ids=list(request.problem_ids),
            problem_count=len(request.problem_ids),
            api_key_id=request.api_key_id,
            budget_cap_usd=request.budget_cap_usd,
            spent_usd=0.0,
            completed_count=0,
            failed_count=0,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        with self._session() as session, session.begin():
            session.add(task)
        return _to_response(task)

    def credential_id(self, evaluation_id: str, owner_id: str) -> str:
        """Return only the owner's credential reference for worker integration."""
        with self._session() as session:
            task = self._owned_task(session, evaluation_id, owner_id)
            return task.api_key_id or ""

    def get_evaluation(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Get evaluation task details."""
        with self._session() as session:
            task = self._owned_task(session, evaluation_id, owner_id)
            return _to_response(task)

    def list_evaluations(
        self, owner_id: str, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[EvaluationResponse], int]:
        """List all evaluation tasks with optional filtering."""
        with self._session() as session:
            query = select(Evaluation).where(Evaluation.user_id == owner_id)
            if status:
                query = query.where(Evaluation.status == status)
            tasks = session.scalars(query.order_by(Evaluation.created_at, Evaluation.id)).all()

        total = len(tasks)
        responses = [_to_response(task) for task in tasks[offset : offset + limit]]
        return responses, total

    def update_evaluation(
        self, evaluation_id: str, request: EvaluationUpdateRequest, owner_id: str
    ) -> EvaluationResponse:
        """Update evaluation task configuration (pending tasks only)."""
        with self._session() as session, session.begin():
            task = self._owned_task(session, evaluation_id, owner_id)
            if task.status != "pending":
                raise ValueError(f"Cannot update task in {task.status} status")
            if request.budget_cap_usd is not None:
                task.budget_cap_usd = request.budget_cap_usd
            task.updated_at = utcnow()
            return _to_response(task)

    def delete_evaluation(
        self, evaluation_id: str, owner_id: str, cleanup: Callable[[], None] | None = None
    ) -> None:
        """Delete evaluation task (pending or completed only).

        Cleanup runs before the row is removed, matching the original
        in-memory semantics: a cleanup failure leaves the row intact so the
        client can retry instead of orphaning associated records.
        """
        with self._session() as session, session.begin():
            task = self._owned_task(session, evaluation_id, owner_id)
            if task.status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Cannot delete task in {task.status} status")
        if cleanup:
            cleanup()
        with self._session() as session, session.begin():
            task = self._owned_task(session, evaluation_id, owner_id)
            if task.status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Cannot delete task in {task.status} status")
            session.delete(task)

    # -- async task support (Task 5) ----------------------------------------

    def create_evaluation_async(
        self, request: EvaluationCreateRequest, owner_id: str
    ) -> EvaluationResponse:
        """Create evaluation and submit Celery async task.

        This is the new async-aware version that:
        1. Creates an Evaluation record
        2. Creates and submits an AsyncTask via TaskManager
        3. Links them together
        4. Returns response with async task status
        """
        session = self._session()
        try:
            task_manager = TaskManager(session)

            # 1. Create Evaluation record
            evaluation = Evaluation(
                id=str(uuid.uuid4()),
                user_id=owner_id,
                status="pending",
                strategy_names=list(request.strategy_names),
                problem_ids=list(request.problem_ids),
                problem_count=len(request.problem_ids),
                api_key_id=request.api_key_id,
                budget_cap_usd=request.budget_cap_usd,
                spent_usd=0.0,
                completed_count=0,
                failed_count=0,
                created_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(evaluation)
            session.flush()

            # 2. Create and submit AsyncTask
            async_task = task_manager.create_task(
                task_type="evaluation",
                entity_id=evaluation.id,
                user_id=owner_id,
                celery_task_name="src.tasks.evaluation.run_evaluation_task",
                celery_task_args=(evaluation.id,),
            )

            # 3. Link AsyncTask to Evaluation
            evaluation.async_task_id = async_task.id
            session.commit()

            return _to_response_async(evaluation, async_task)
        finally:
            session.close()

    def get_evaluation_async(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Get evaluation with aggregated AsyncTask status.

        Returns the evaluation with status aggregated from AsyncTask if present.
        """
        session = self._session()
        try:
            task = self._owned_task(session, evaluation_id, owner_id)

            # Load async task if linked
            async_task = None
            if task.async_task_id:
                async_task = session.get(AsyncTask, task.async_task_id)

            return _to_response_async(task, async_task)
        finally:
            session.close()

    def pause_evaluation(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Pause a running evaluation task.

        Only pauses if:
        - Evaluation exists and belongs to owner
        - Evaluation has an associated AsyncTask
        - AsyncTask is in running state
        """
        session = self._session()
        try:
            evaluation = self._owned_task(session, evaluation_id, owner_id)

            if not evaluation.async_task_id:
                raise ValueError("Evaluation has no associated task")

            # Load and pause the async task
            task_manager = TaskManager(session)
            async_task = task_manager.pause_task(evaluation.async_task_id, owner_id)

            return _to_response_async(evaluation, async_task)
        finally:
            session.close()

    def resume_evaluation(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Resume a paused or failed evaluation task.

        Creates a new AsyncTask to resume execution from the checkpoint.
        """
        session = self._session()
        try:
            evaluation = self._owned_task(session, evaluation_id, owner_id)

            if not evaluation.async_task_id:
                raise ValueError("Evaluation has no associated task")

            task_manager = TaskManager(session)

            # Verify old task is in resumable state
            old_task = task_manager.get_task(evaluation.async_task_id, owner_id)
            if old_task.status not in ("paused", "failed"):
                raise ValueError(
                    f"Cannot resume evaluation in status '{old_task.status}'; only 'paused' or 'failed' tasks can resume"
                )

            # Create new task for resume
            new_task = task_manager.create_task(
                task_type="evaluation",
                entity_id=evaluation.id,
                user_id=owner_id,
                celery_task_name="src.tasks.evaluation.run_evaluation_task",
                celery_task_args=(evaluation.id,),
            )

            # Update evaluation to link new task and set to pending
            evaluation.async_task_id = new_task.id
            evaluation.status = "pending"
            session.commit()

            return _to_response_async(evaluation, new_task)
        finally:
            session.close()

    def delete_evaluation_async(self, evaluation_id: str, owner_id: str) -> None:
        """Delete evaluation and cancel associated async task.

        Cancels the Celery task and removes both AsyncTask and Evaluation records.
        """
        session = self._session()
        try:
            evaluation = self._owned_task(session, evaluation_id, owner_id)

            # Cancel async task if present
            if evaluation.async_task_id:
                task_manager = TaskManager(session)
                try:
                    task_manager.cancel_task(evaluation.async_task_id, owner_id)
                except ValueError:
                    # Task already in terminal state, ignore
                    pass

                # Delete the AsyncTask record
                session.query(AsyncTask).filter(AsyncTask.id == evaluation.async_task_id).delete()

            # Delete the Evaluation record
            session.delete(evaluation)
            session.commit()
        finally:
            session.close()

    # -- lifecycle -----------------------------------------------------------

    def start_evaluation(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Start evaluation task execution in background."""
        with self._session() as session, session.begin():
            task = self._owned_task(session, evaluation_id, owner_id)
            if task.status != "pending":
                raise ValueError(f"Cannot start task in {task.status} status")
            task.status = "running"
            task.started_at = utcnow()
            task.updated_at = utcnow()
            response = _to_response(task)

        thread = threading.Thread(target=self._execute_task, args=(evaluation_id,), daemon=True)
        thread.start()
        return response

    def cancel_evaluation(self, evaluation_id: str, owner_id: str) -> EvaluationResponse:
        """Cancel running evaluation task."""
        with self._session() as session, session.begin():
            task = self._owned_task(session, evaluation_id, owner_id)
            if task.status != "running":
                raise ValueError(f"Cannot cancel task in {task.status} status")
            task.status = "cancelled"
            task.updated_at = utcnow()
            return _to_response(task)

    def get_progress(self, evaluation_id: str, owner_id: str) -> ProgressInfo:
        """Get task execution progress."""
        with self._session() as session:
            task = self._owned_task(session, evaluation_id, owner_id)
            percentage = (
                (task.completed_count / task.problem_count * 100) if task.problem_count else 0
            )
            return ProgressInfo(
                current=task.completed_count,
                total=task.problem_count,
                message=None,
                completed=task.completed_count,
                percentage=percentage,
            )

    # -- execution -----------------------------------------------------------

    def _execute_task(self, evaluation_id: str) -> None:
        """Execute task in background (simulated)."""
        # Acquire semaphore to limit concurrent execution
        with self._concurrent_semaphore:
            try:
                with self._session() as session:
                    task = session.get(Evaluation, evaluation_id)
                if not task or task.status != "running":
                    return
                self._run_simulated(evaluation_id)
            except Exception as e:  # noqa: BLE001 - reported on the task row
                self._fail(evaluation_id, str(e))

    def _run_simulated(self, evaluation_id: str) -> None:
        with self._session() as session:
            task = session.get(Evaluation, evaluation_id)
            if task is None:
                return
            strategy_count = len(task.strategy_names)
            problem_count = task.problem_count
            budget_cap_usd = task.budget_cap_usd
        total_executions = strategy_count * problem_count

        for i in range(total_executions):
            if self._status_of(evaluation_id) != "running":
                return
            time.sleep(0.05)
            self._record_tick(evaluation_id, i, problem_count)
            if budget_cap_usd and self._spent_of(evaluation_id) >= budget_cap_usd:
                self._finish(evaluation_id, "completed", "Budget exceeded")
                return
        self._finish(evaluation_id, "completed", None)

    def _status_of(self, evaluation_id: str) -> str | None:
        with self._session() as session:
            task = session.get(Evaluation, evaluation_id)
            return task.status if task else None

    def _record_tick(self, evaluation_id: str, index: int, problem_count: int) -> str:
        """Persist one execution tick; return the task status after the write."""
        with self._session() as session, session.begin():
            task = session.get(Evaluation, evaluation_id, with_for_update=True)
            if task is None:
                return "failed"
            if task.status == "running":
                task.completed_count = min(index + 1, problem_count)
                task.spent_usd += 0.01
                task.updated_at = utcnow()
            return task.status

    def close(self) -> None:
        """Release pooled connections (lifespan shutdown hygiene)."""
        self._engine.dispose()

    def _spent_of(self, evaluation_id: str) -> float:
        with self._session() as session:
            task = session.get(Evaluation, evaluation_id)
            return task.spent_usd if task else 0.0

    def _finish(self, evaluation_id: str, status: str, error_message: str | None) -> None:
        with self._session() as session, session.begin():
            task = session.get(Evaluation, evaluation_id, with_for_update=True)
            if task is None or task.status not in ("pending", "running"):
                return
            task.status = status
            task.error_message = error_message
            task.completed_at = utcnow()
            task.updated_at = utcnow()

    def _fail(self, evaluation_id: str, message: str) -> None:
        with self._session() as session, session.begin():
            task = session.get(Evaluation, evaluation_id, with_for_update=True)
            if task is None or task.status in _TERMINAL_STATUSES:
                return
            task.status = "failed"
            task.error_message = message
            task.updated_at = utcnow()
