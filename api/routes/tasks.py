"""Async task management endpoints."""

from collections.abc import Callable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from api.auth.dependencies import current_user
from api.auth.service import Principal
from api.db.engine import get_db
from api.models import AsyncTaskCreateRequest
from api.schemas import ApiResponse, AsyncTaskResponse, PaginatedData
from src.task_manager import TaskManager

router = APIRouter(prefix="/api/v1", tags=["tasks"])
T = TypeVar("T")

# Public submission must not expose internal Celery workers (e.g. global cleanup).
_PUBLIC_TASKS = {
    "evaluation": "src.tasks.evaluation.run_evaluation_task",
    "experiment": "src.tasks.experiment.run_experiment_task",
    "import": "src.tasks.imports.run_import_task",
    "benchmark": "src.tasks.benchmark.run_benchmark_task",
}


def task_manager(request: Request, db: Session = Depends(get_db)) -> TaskManager:
    """Get TaskManager instance."""
    return TaskManager(db, file_store=request.app.state.files.store)


def call(operation: Callable[[], T]) -> T:
    """Execute operation with error handling."""
    try:
        return operation()
    except ValueError as exc:
        error_msg = str(exc).lower()
        if "not found" in error_msg:
            raise HTTPException(404, str(exc)) from None
        else:
            raise HTTPException(400, str(exc)) from None


def task_to_response(task) -> AsyncTaskResponse:
    """Convert AsyncTask model to response schema."""
    return AsyncTaskResponse(
        id=task.id,
        task_type=task.task_type,
        entity_id=task.entity_id,
        celery_task_id=task.celery_task_id,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at.isoformat() if task.created_at else None,
        started_at=task.started_at.isoformat() if task.started_at else None,
        completed_at=task.completed_at.isoformat() if task.completed_at else None,
        updated_at=task.updated_at.isoformat() if task.updated_at else None,
    )


@router.post("/tasks", status_code=201)
def create_task(
    request: AsyncTaskCreateRequest,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[AsyncTaskResponse]:
    """Create a new async task.

    Creates an async task and submits it to Celery for execution.

    Args:
        request: Task creation request with task_type, entity_id, and celery task details
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with created task details
    """
    if _PUBLIC_TASKS.get(request.task_type) != request.celery_task_name:
        raise HTTPException(403, "Task is not allowed for public submission")

    task_args = tuple(request.celery_task_args) if request.celery_task_args else ()
    task_kwargs = request.celery_task_kwargs or {}

    task = call(
        lambda: manager.enqueue_task(
            task_type=request.task_type,
            entity_id=request.entity_id,
            user_id=principal.user_id,
            celery_task_name=request.celery_task_name,
            celery_task_args=task_args,
            celery_task_kwargs=task_kwargs,
        )
    )

    return ApiResponse(
        success=True,
        data=task_to_response(task),
        message="Task created successfully",
    )


@router.get("/tasks/{task_id}")
def get_task(
    task_id: str,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[AsyncTaskResponse]:
    """Get task status and details.

    Retrieves the current status of an async task, including progress information.

    Args:
        task_id: Task ID to retrieve
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with task details
    """
    task = call(lambda: manager.get_task(task_id, principal.user_id))
    return ApiResponse(
        success=True,
        data=task_to_response(task),
        message="Task retrieved successfully",
    )


@router.delete("/tasks/{task_id}")
def cancel_task(
    task_id: str,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[AsyncTaskResponse]:
    """Cancel a running or pending task.

    Terminates the task execution in Celery and marks it as cancelled.

    Args:
        task_id: Task ID to cancel
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with cancelled task details
    """
    task = call(lambda: manager.cancel_task(task_id, principal.user_id))
    return ApiResponse(
        success=True,
        data=task_to_response(task),
        message="Task cancelled successfully",
    )


@router.post("/tasks/{task_id}/pause")
def pause_task(
    task_id: str,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[AsyncTaskResponse]:
    """Pause a running task.

    Pauses a running task. The task can be resumed later.

    Args:
        task_id: Task ID to pause
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with paused task details
    """
    task = call(lambda: manager.pause_task(task_id, principal.user_id))
    return ApiResponse(
        success=True,
        data=task_to_response(task),
        message="Task paused successfully",
    )


@router.post("/tasks/{task_id}/resume")
def resume_task(
    task_id: str,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[AsyncTaskResponse]:
    """Resume a paused evaluation, experiment, benchmark, import or A/B task.

    Re-queues the same task after committing its pending business status.
    Business workers must confirm stopping before resume is accepted.

    Args:
        task_id: Task ID to resume
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with the same task, now pending
    """
    task = call(lambda: manager.resume_task(task_id, principal.user_id))
    return ApiResponse(
        success=True,
        data=task_to_response(task),
        message="Task resumed successfully",
    )


@router.get("/tasks")
def list_tasks(
    status: str | None = None,
    task_type: str | None = None,
    limit: int = 20,
    offset: int = 0,
    principal: Principal = Depends(current_user),
    manager: TaskManager = Depends(task_manager),
) -> ApiResponse[PaginatedData[AsyncTaskResponse]]:
    """List async tasks for the authenticated user.

    Retrieves a paginated list of async tasks with optional filtering by status and type.

    Args:
        status: Optional status filter (pending, running, paused, completed, failed, cancelled)
        task_type: Optional task type filter
        limit: Number of items per page (1-100, default 20)
        offset: Number of items to skip (default 0)
        principal: Authenticated user
        manager: TaskManager instance

    Returns:
        ApiResponse with paginated task list
    """
    limit = limit if 1 <= limit <= 100 else 20
    offset = max(0, offset)

    tasks, total = call(
        lambda: manager.list_tasks(
            user_id=principal.user_id,
            task_type=task_type,
            status=status,
            limit=limit,
            offset=offset,
        )
    )

    data = PaginatedData(
        items=[task_to_response(task) for task in tasks],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + limit < total,
    )

    return ApiResponse(
        success=True,
        data=data,
        message="Tasks retrieved successfully",
    )
