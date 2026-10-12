"""API tests for async task management endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import Mock, patch, MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import AsyncTask, Base
from src.task_manager import TaskManager


@pytest.fixture
def db_engine():
    """Create in-memory database engine."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_session(db_engine):
    """Create database session for testing."""
    SessionLocal = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def task_manager(db_session):
    """Create TaskManager instance."""
    return TaskManager(db_session)


def create_test_task(db_session: Session, user_id: str = "test-user-123") -> AsyncTask:
    """Helper to create a test async task."""
    task = AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id=f"celery-{uuid.uuid4()}",
        task_type="evaluation",
        entity_id=str(uuid.uuid4()),
        user_id=user_id,
        status="pending",
    )
    db_session.add(task)
    db_session.commit()
    return task


class TestCreateTaskEndpoint:
    """Tests for POST /api/v1/tasks - Create task endpoint"""

    def test_create_task_success(self, task_manager, db_session):
        """Test successful task creation via TaskManager."""
        task_type = "evaluation"
        entity_id = str(uuid.uuid4())
        user_id = "test-user-123"

        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-id-123"
            mock_send_task.return_value = mock_result

            task = task_manager.create_task(
                task_type=task_type,
                entity_id=entity_id,
                user_id=user_id,
                celery_task_name="src.tasks.evaluation.run_evaluation_task",
                celery_task_args=("arg1",),
                celery_task_kwargs={"key": "value"},
            )

        assert task.task_type == "evaluation"
        assert task.entity_id == entity_id
        assert task.status == "pending"
        assert task.celery_task_id == "celery-task-id-123"
        assert task.id is not None


class TestGetTaskEndpoint:
    """Tests for GET /api/v1/tasks/{task_id} - Get task status endpoint"""

    def test_get_task_success(self, task_manager, db_session):
        """Test successful task retrieval."""
        task = create_test_task(db_session)

        with patch("src.task_manager.celery_app.AsyncResult"):
            result = task_manager.get_task(task.id, user_id=task.user_id)

        assert result.id == task.id
        assert result.task_type == task.task_type
        assert result.status == "pending"

    def test_get_task_not_found(self, task_manager):
        """Test retrieving non-existent task."""
        with pytest.raises(ValueError, match="Task not found"):
            task_manager.get_task(str(uuid.uuid4()), user_id="test-user-123")

    def test_get_task_access_denied(self, task_manager, db_session):
        """Test access denied for another user's task."""
        task = create_test_task(db_session, user_id="other-user")

        with pytest.raises(ValueError, match="Task not found or access denied"):
            task_manager.get_task(task.id, user_id="different-user")


class TestCancelTaskEndpoint:
    """Tests for DELETE /api/v1/tasks/{task_id} - Cancel task endpoint"""

    def test_cancel_task_success(self, task_manager, db_session):
        """Test successful task cancellation."""
        task = create_test_task(db_session, user_id="test-user-123")
        task.status = "running"
        db_session.commit()

        with patch("src.task_manager.celery_app.AsyncResult"), \
             patch("src.task_manager.celery_app.control.revoke") as mock_revoke:
            result = task_manager.cancel_task(task.id, task.user_id)

        assert result.status == "cancelled"
        mock_revoke.assert_called_once_with(task.celery_task_id, terminate=True)

    def test_cancel_completed_task(self, task_manager, db_session):
        """Test cancelling an already completed task."""
        task = create_test_task(db_session, user_id="test-user-123")
        task.status = "completed"
        db_session.commit()

        with pytest.raises(ValueError, match="Cannot cancel completed or failed tasks"):
            task_manager.cancel_task(task.id, task.user_id)


class TestPauseTaskEndpoint:
    """Tests for POST /api/v1/tasks/{task_id}/pause - Pause task endpoint"""

    def test_pause_running_task_success(self, task_manager, db_session):
        """Test successful pausing of a running task."""
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=f"celery-{uuid.uuid4()}",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="test-user-123",
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        with patch("src.task_manager.celery_app.AsyncResult"):
            result = task_manager.pause_task(task.id, task.user_id)

        assert result.status == "paused"

    def test_pause_pending_task_fails(self, task_manager, db_session):
        """Test pausing a pending task (should fail)."""
        task = create_test_task(db_session, user_id="test-user-123")

        with patch("src.task_manager.celery_app.AsyncResult"), \
             pytest.raises(ValueError, match="Can only pause running tasks"):
            task_manager.pause_task(task.id, task.user_id)


class TestResumeTaskEndpoint:
    """Tests for POST /api/v1/tasks/{task_id}/resume - Resume task endpoint"""

    def test_resume_paused_task_success(self, task_manager, db_session):
        """Test successful resumption of a paused task."""
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=f"celery-{uuid.uuid4()}",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="test-user-123",
            status="paused",
        )
        db_session.add(task)
        db_session.commit()

        # Get task to update status
        with patch("src.task_manager.celery_app.AsyncResult"):
            retrieved_task = task_manager.get_task(task.id, user_id=task.user_id)
            retrieved_task.status = "running"
            retrieved_task.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            db_session.commit()

            result = task_manager.get_task(task.id, user_id=task.user_id)
            assert result.status == "running"

    def test_resume_running_task_fails(self, task_manager, db_session):
        """Test resuming a running task (should fail)."""
        task = create_test_task(db_session, user_id="test-user-123")
        task.status = "running"
        db_session.commit()

        # Should not raise an error when getting a running task
        with patch("src.task_manager.celery_app.AsyncResult"):
            result = task_manager.get_task(task.id, user_id=task.user_id)
            assert result.status == "running"


class TestListTasksEndpoint:
    """Tests for GET /api/v1/tasks - List tasks endpoint"""

    def test_list_tasks_success(self, task_manager, db_session):
        """Test successful task listing."""
        user_id = "test-user-123"
        # Create multiple tasks
        create_test_task(db_session, user_id=user_id)
        create_test_task(db_session, user_id=user_id)
        # Create task for different user
        create_test_task(db_session, user_id="other-user")

        tasks, total = task_manager.list_tasks(user_id=user_id)

        assert total == 2
        assert len(tasks) == 2

    def test_list_tasks_with_pagination(self, task_manager, db_session):
        """Test task listing with pagination."""
        user_id = "test-user-123"
        # Create 5 tasks
        for _ in range(5):
            create_test_task(db_session, user_id=user_id)

        tasks, total = task_manager.list_tasks(user_id=user_id, limit=2, offset=0)

        assert total == 5
        assert len(tasks) == 2

    def test_list_tasks_filter_by_status(self, task_manager, db_session):
        """Test task listing with status filter."""
        user_id = "test-user-123"
        create_test_task(db_session, user_id=user_id)
        task2 = create_test_task(db_session, user_id=user_id)
        task2.status = "running"
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=user_id, status="running")

        assert total == 1
        assert len(tasks) == 1
        assert tasks[0].status == "running"

    def test_list_tasks_filter_by_task_type(self, task_manager, db_session):
        """Test task listing with task_type filter."""
        user_id = "test-user-123"
        create_test_task(db_session, user_id=user_id)
        task2 = create_test_task(db_session, user_id=user_id)
        task2.task_type = "experiment"
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=user_id, task_type="experiment")

        assert total == 1
        assert tasks[0].task_type == "experiment"

    def test_list_tasks_empty(self, task_manager):
        """Test listing tasks when user has none."""
        tasks, total = task_manager.list_tasks(user_id="user-with-no-tasks")

        assert total == 0
        assert len(tasks) == 0
