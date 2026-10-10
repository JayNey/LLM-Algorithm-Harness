"""Service layer for evaluation task management."""

import uuid
import threading
import time
from datetime import datetime
from typing import Optional, Dict, Any
from threading import Semaphore

from api.models import EvaluationCreateRequest, EvaluationUpdateRequest
from api.schemas import EvaluationResponse, ProgressInfo
from api.config import settings


class TaskState:
    """In-memory task state."""

    def __init__(self, task_id: str, request: EvaluationCreateRequest):
        self.task_id = task_id
        self.created_at = datetime.utcnow().isoformat() + "Z"
        self.updated_at = self.created_at
        self.status = "pending"  # pending, running, completed, failed, cancelled
        self.strategy_names = request.strategy_names
        self.problem_ids = request.problem_ids
        self.problem_count = len(request.problem_ids)
        self.budget_cap_usd = request.budget_cap_usd
        self.spent_usd = 0.0
        self.completed_count = 0
        self.failed_count = 0
        self.error_message: Optional[str] = None
        self._lock = threading.Lock()

    def to_response(self) -> EvaluationResponse:
        """Convert to API response."""
        with self._lock:
            percentage = (self.completed_count / self.problem_count * 100) if self.problem_count > 0 else 0
            return EvaluationResponse(
                evaluation_id=self.task_id,
                created_at=self.created_at,
                updated_at=self.updated_at,
                status=self.status,
                strategy_names=self.strategy_names,
                problem_count=self.problem_count,
                spent_usd=self.spent_usd,
                budget_cap_usd=self.budget_cap_usd,
                progress=ProgressInfo(
                    completed=self.completed_count,
                    total=self.problem_count,
                    percentage=percentage,
                ),
            )


class EvaluationService:
    """Service for managing evaluation tasks."""

    def __init__(self):
        """Initialize evaluation service."""
        self.tasks: Dict[str, TaskState] = {}
        self._tasks_lock = threading.Lock()
        self._concurrent_semaphore = Semaphore(settings.MAX_CONCURRENT_TASKS)

    def create_evaluation(self, request: EvaluationCreateRequest) -> EvaluationResponse:
        """Create a new evaluation task."""
        task_id = str(uuid.uuid4())
        task = TaskState(task_id, request)

        with self._tasks_lock:
            self.tasks[task_id] = task

        return task.to_response()

    def get_evaluation(self, evaluation_id: str) -> EvaluationResponse:
        """Get evaluation task details."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")
            task = self.tasks[evaluation_id]

        return task.to_response()

    def list_evaluations(
        self, status: Optional[str] = None, limit: int = 20, offset: int = 0
    ) -> tuple[list[EvaluationResponse], int]:
        """List all evaluation tasks with optional filtering."""
        with self._tasks_lock:
            tasks = list(self.tasks.values())

        # Filter by status if provided
        if status:
            tasks = [t for t in tasks if t.status == status]

        # Get total before pagination
        total = len(tasks)

        # Apply pagination
        paginated_tasks = tasks[offset : offset + limit]

        # Convert to responses
        responses = [t.to_response() for t in paginated_tasks]

        return responses, total

    def update_evaluation(
        self, evaluation_id: str, request: EvaluationUpdateRequest
    ) -> EvaluationResponse:
        """Update evaluation task configuration (pending tasks only)."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")

            task = self.tasks[evaluation_id]

            # Only pending tasks can be updated
            if task.status != "pending":
                raise ValueError(f"Cannot update task in {task.status} status")

            # Update allowed fields
            if request.budget_cap_usd is not None:
                task.budget_cap_usd = request.budget_cap_usd
            task.updated_at = datetime.utcnow().isoformat() + "Z"

        return task.to_response()

    def delete_evaluation(self, evaluation_id: str) -> None:
        """Delete evaluation task (pending or completed only)."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")

            task = self.tasks[evaluation_id]

            # Only pending or completed tasks can be deleted
            if task.status not in ("pending", "completed", "cancelled"):
                raise ValueError(f"Cannot delete task in {task.status} status")

            del self.tasks[evaluation_id]

    def start_evaluation(self, evaluation_id: str) -> EvaluationResponse:
        """Start evaluation task execution in background."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")

            task = self.tasks[evaluation_id]

            # Only pending tasks can be started
            if task.status != "pending":
                raise ValueError(f"Cannot start task in {task.status} status")

            task.status = "running"
            task.updated_at = datetime.utcnow().isoformat() + "Z"

        # Start background execution
        thread = threading.Thread(
            target=self._execute_task, args=(evaluation_id,), daemon=True
        )
        thread.start()

        return task.to_response()

    def cancel_evaluation(self, evaluation_id: str) -> EvaluationResponse:
        """Cancel running evaluation task."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")

            task = self.tasks[evaluation_id]

            # Only running tasks can be cancelled
            if task.status != "running":
                raise ValueError(f"Cannot cancel task in {task.status} status")

            task.status = "cancelled"
            task.updated_at = datetime.utcnow().isoformat() + "Z"

        return task.to_response()

    def get_progress(self, evaluation_id: str) -> ProgressInfo:
        """Get task execution progress."""
        with self._tasks_lock:
            if evaluation_id not in self.tasks:
                raise ValueError(f"Evaluation {evaluation_id} not found")
            task = self.tasks[evaluation_id]

        with task._lock:
            percentage = (task.completed_count / task.problem_count * 100) if task.problem_count > 0 else 0
            return ProgressInfo(
                completed=task.completed_count,
                total=task.problem_count,
                percentage=percentage,
            )

    def _execute_task(self, evaluation_id: str) -> None:
        """Execute task in background (simulated)."""
        # Acquire semaphore to limit concurrent execution
        with self._concurrent_semaphore:
            try:
                with self._tasks_lock:
                    task = self.tasks.get(evaluation_id)

                if not task or task.status != "running":
                    return

                # Simulate task execution with progress updates
                problems_per_strategy = task.problem_count  # Simplified: 1 execution per problem
                total_executions = len(task.strategy_names) * problems_per_strategy

                for i in range(total_executions):
                    if task.status != "running":
                        break

                    # Simulate work (50ms per problem)
                    time.sleep(0.05)

                    with task._lock:
                        task.completed_count = min(
                            i + 1, task.problem_count
                        )  # Cap at problem count
                        # Simulate cost accumulation
                        task.spent_usd += 0.01

                    # Check budget exceeded
                    if (task.budget_cap_usd and
                        task.spent_usd >= task.budget_cap_usd and
                        task.status == "running"):
                        with task._lock:
                            task.status = "completed"
                            task.error_message = "Budget exceeded"
                        return

                # Mark as completed
                with task._lock:
                    task.status = "completed"
                    task.updated_at = datetime.utcnow().isoformat() + "Z"

            except Exception as e:
                with self._tasks_lock:
                    task = self.tasks.get(evaluation_id)
                    if task:
                        with task._lock:
                            task.status = "failed"
                            task.error_message = str(e)
                            task.updated_at = datetime.utcnow().isoformat() + "Z"


# Global service instance
evaluation_service = EvaluationService()
