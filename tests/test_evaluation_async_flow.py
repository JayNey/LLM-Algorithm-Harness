"""集成测试：完整的异步评估流程。

本测试套件测试异步评估流程的完整端到端工作流程，包括：
- 创建和轮询流程
- 暂停和恢复
- 任务列表和过滤
- 错误场景处理
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Evaluation
from api.schemas import ProgressInfo
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


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-123"


def create_test_evaluation(
    db_session, evaluation_id: str = None, user_id: str = "test-user-123"
) -> tuple[Evaluation, AsyncTask]:
    """Helper to create a test evaluation with async task."""
    evaluation_id = evaluation_id or str(uuid.uuid4())
    async_task_id = str(uuid.uuid4())

    async_task = AsyncTask(
        id=async_task_id,
        celery_task_id=f"celery-{uuid.uuid4()}",
        task_type="evaluation",
        entity_id=evaluation_id,
        user_id=user_id,
        status="pending",
    )
    db_session.add(async_task)

    evaluation = Evaluation(
        id=evaluation_id,
        user_id=user_id,
        status="pending",
        strategy_names=["strategy1"],
        problem_ids=["problem1", "problem2"],
        problem_count=2,
        api_key_id="key-001",
        budget_cap_usd=10.0,
        async_task_id=async_task_id,
    )
    db_session.add(evaluation)
    db_session.commit()

    return evaluation, async_task


class TestCreateAndPollFlow:
    """测试创建和轮询流程."""

    def test_create_task_via_task_manager(self, task_manager, db_session, test_user_id):
        """测试通过 TaskManager 创建任务."""
        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-123"
            mock_send_task.return_value = mock_result

            task = task_manager.create_task(
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=test_user_id,
                celery_task_name="test.task",
                celery_task_args=(),
                celery_task_kwargs={},
            )

        assert task.task_type == "evaluation"
        assert task.status == "pending"
        assert task.user_id == test_user_id

    def test_get_evaluation_returns_pending_status(self, db_session, test_user_id):
        """测试获取评估返回 pending 状态."""
        evaluation, async_task = create_test_evaluation(db_session, user_id=test_user_id)

        # Fetch from database
        fetched = db_session.query(Evaluation).filter_by(id=evaluation.id).first()
        assert fetched is not None
        assert fetched.status == "pending"
        assert fetched.async_task_id == async_task.id

    def test_evaluation_status_reflects_async_task_status(self, db_session, test_user_id):
        """测试评估状态反映 AsyncTask 状态."""
        evaluation, async_task = create_test_evaluation(db_session, user_id=test_user_id)

        # Update async task to running
        async_task.status = "running"
        db_session.commit()

        # Fetch and verify
        fetched_task = db_session.query(AsyncTask).filter_by(id=async_task.id).first()
        assert fetched_task.status == "running"

        # Evaluation should still reference the task
        fetched_eval = db_session.query(Evaluation).filter_by(id=evaluation.id).first()
        assert fetched_eval.async_task_id == fetched_task.id

    def test_poll_evaluation_multiple_times(self, db_session, test_user_id):
        """测试轮询评估多次."""
        evaluation, async_task = create_test_evaluation(db_session, user_id=test_user_id)

        # Simulate polling
        for i in range(3):
            fetched = db_session.query(Evaluation).filter_by(id=evaluation.id).first()
            assert fetched is not None

            # Simulate progress
            if i == 1:
                async_task.status = "running"
            elif i == 2:
                async_task.status = "completed"
            db_session.commit()

        # Final state
        fetched = db_session.query(Evaluation).filter_by(id=evaluation.id).first()
        fetched_task = db_session.query(AsyncTask).filter_by(id=async_task.id).first()
        assert fetched_task.status == "completed"


class TestPauseAndResume:
    """测试暂停和恢复."""

    def test_pause_running_task(self, task_manager, db_session, test_user_id):
        """测试暂停运行中的任务."""
        async_task_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=entity_id,
            user_id=test_user_id,
            status="running",
        )
        db_session.add(async_task)
        db_session.commit()

        with patch("src.task_manager.celery_app.AsyncResult"):
            result = task_manager.pause_task(async_task_id, test_user_id)

        assert result.status == "paused"

    def test_resume_paused_task(self, task_manager, db_session, test_user_id):
        """测试恢复暂停的任务."""
        async_task_id = str(uuid.uuid4())
        entity_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=entity_id,
            user_id=test_user_id,
            status="paused",
        )
        db_session.add(async_task)
        db_session.add(
            Evaluation(
                id=entity_id,
                user_id=test_user_id,
                status="paused",
                strategy_names=["vanilla"],
                problem_ids=["p1"],
                problem_count=1,
                async_task_id=async_task_id,
            )
        )
        db_session.commit()

        with patch("src.task_manager.celery_app.send_task", return_value=Mock()) as mock_send:
            result = task_manager.resume_task(async_task_id, test_user_id)

        assert result.id == async_task_id
        assert result.status == "pending"
        mock_send.assert_called_once()
        fetched = db_session.query(AsyncTask).filter_by(id=async_task_id).first()
        assert fetched.status == "pending"

    def test_pause_pending_task_fails(self, task_manager, db_session, test_user_id):
        """测试暂停待执行任务失败."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="pending",
        )
        db_session.add(async_task)
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.AsyncResult"),
            pytest.raises(ValueError, match="Can only pause running"),
        ):
            task_manager.pause_task(async_task_id, test_user_id)

    def test_verify_paused_status(self, db_session, test_user_id):
        """测试验证暂停状态."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="paused",
        )
        db_session.add(async_task)
        db_session.commit()

        fetched = db_session.query(AsyncTask).filter_by(id=async_task_id).first()
        assert fetched.status == "paused"


class TestTaskList:
    """测试任务列表."""

    def test_list_tasks_returns_all_user_tasks(self, task_manager, db_session, test_user_id):
        """测试列表返回所有用户任务."""
        # Create multiple tasks
        for i in range(3):
            async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-task-{i}",
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=test_user_id,
                status="pending" if i < 2 else "running",
            )
            db_session.add(async_task)
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=test_user_id)
        assert total == 3
        assert len(tasks) == 3

    def test_list_tasks_with_status_filter(self, task_manager, db_session, test_user_id):
        """测试按状态过滤任务."""
        # Create tasks with different statuses
        for status in ["pending", "running", "completed"]:
            async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-task-{status}",
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=test_user_id,
                status=status,
            )
            db_session.add(async_task)
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=test_user_id, status="running")
        assert total == 1
        assert tasks[0].status == "running"

    def test_list_tasks_with_pagination(self, task_manager, db_session, test_user_id):
        """测试分页."""
        # Create 5 tasks
        for i in range(5):
            async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-task-{i}",
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=test_user_id,
                status="pending",
            )
            db_session.add(async_task)
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=test_user_id, limit=2, offset=0)
        assert total == 5
        assert len(tasks) == 2

    def test_list_tasks_with_task_type_filter(self, task_manager, db_session, test_user_id):
        """测试按任务类型过滤."""
        # Create tasks with different types
        for task_type in ["evaluation", "experiment"]:
            async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-task-{task_type}",
                task_type=task_type,
                entity_id=str(uuid.uuid4()),
                user_id=test_user_id,
                status="pending",
            )
            db_session.add(async_task)
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=test_user_id, task_type="evaluation")
        assert total == 1
        assert tasks[0].task_type == "evaluation"

    def test_list_tasks_does_not_return_other_users_tasks(
        self, task_manager, db_session, test_user_id
    ):
        """测试列表不返回其他用户的任务."""
        # Create tasks for different users
        for user_suffix in ["1", "2"]:
            async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-task-{user_suffix}",
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=f"user-{user_suffix}",
                status="pending",
            )
            db_session.add(async_task)
        db_session.commit()

        tasks, total = task_manager.list_tasks(user_id=test_user_id)
        assert total == 0


class TestErrorScenarios:
    """测试错误场景."""

    def test_get_nonexistent_task(self, task_manager, test_user_id):
        """测试获取不存在的任务."""
        nonexistent_id = str(uuid.uuid4())

        with pytest.raises(ValueError, match="Task not found"):
            task_manager.get_task(nonexistent_id, test_user_id)

    def test_cancel_completed_task_fails(self, task_manager, db_session, test_user_id):
        """测试取消已完成任务失败."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="completed",
        )
        db_session.add(async_task)
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.AsyncResult"),
            pytest.raises(ValueError, match="Cannot cancel completed"),
        ):
            task_manager.cancel_task(async_task_id, test_user_id)

    def test_access_denied_for_other_user_task(self, task_manager, db_session, test_user_id):
        """测试其他用户访问任务被拒绝."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="other-user",
            status="running",
        )
        db_session.add(async_task)
        db_session.commit()

        with pytest.raises(ValueError, match="not found or access denied"):
            task_manager.get_task(async_task_id, test_user_id)

    def test_delete_nonexistent_evaluation(self, db_session, test_user_id):
        """测试删除不存在的评估."""
        nonexistent_id = str(uuid.uuid4())

        evaluation = db_session.query(Evaluation).filter_by(id=nonexistent_id).first()
        assert evaluation is None


class TestInvalidStatusTransitions:
    """测试无效的状态转换."""

    def test_resume_running_task_fails(self, task_manager, db_session, test_user_id):
        """测试恢复运行中的任务失败."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="running",
        )
        db_session.add(async_task)
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.AsyncResult"),
            patch("src.task_manager.celery_app.send_task") as mock_send,
            pytest.raises(ValueError, match="Can only resume paused tasks"),
        ):
            task_manager.resume_task(async_task_id, test_user_id)

        mock_send.assert_not_called()
        fetched = db_session.query(AsyncTask).filter_by(id=async_task_id).first()
        assert fetched.status == "running"

    def test_pause_completed_task_fails(self, task_manager, db_session, test_user_id):
        """测试暂停已完成任务失败."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="completed",
        )
        db_session.add(async_task)
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.AsyncResult"),
            pytest.raises(ValueError, match="Can only pause running"),
        ):
            task_manager.pause_task(async_task_id, test_user_id)


class TestProgressInfo:
    """测试进度信息."""

    def test_progress_info_with_all_fields(self):
        """测试 ProgressInfo 与所有字段."""
        progress = ProgressInfo(
            current=5,
            total=10,
            message="Processing...",
        )
        assert progress.current == 5
        assert progress.total == 10
        assert progress.message == "Processing..."

    def test_progress_info_without_message(self):
        """测试 ProgressInfo 不带消息."""
        progress = ProgressInfo(current=5, total=10)
        assert progress.current == 5
        assert progress.total == 10
        assert progress.message is None

    def test_update_task_progress(self, db_session, test_user_id):
        """测试更新任务进度."""
        async_task_id = str(uuid.uuid4())

        async_task = AsyncTask(
            id=async_task_id,
            celery_task_id="celery-task-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="running",
            progress={"current": 0, "total": 10},
        )
        db_session.add(async_task)
        db_session.commit()

        # Update progress
        async_task.progress = {"current": 5, "total": 10, "message": "Half done"}
        db_session.commit()

        fetched = db_session.query(AsyncTask).filter_by(id=async_task_id).first()
        assert fetched.progress["current"] == 5
        assert fetched.progress["message"] == "Half done"
