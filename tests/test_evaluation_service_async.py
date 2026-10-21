"""Test suite for EvaluationService with async task support.

Following TDD approach: tests first, then implementation.
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Evaluation
from api.models import EvaluationCreateRequest
from api.schemas import EvaluationResponse, ExecutionProgress, ProgressInfo


@pytest.fixture
def test_db_session():
    """Create an in-memory SQLite session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def test_user_id():
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def create_request():
    """Sample evaluation create request."""
    return EvaluationCreateRequest(
        strategy_names=["strategy_a", "strategy_b"],
        problem_ids=["problem_1", "problem_2", "problem_3"],
        api_key_id="key-123",
        budget_cap_usd=100.0,
        model="gpt-4o-mini",
    )


@pytest.fixture
def evaluation_with_task(test_db_session, test_user_id):
    """Create an evaluation with an async task."""
    evaluation_id = str(uuid.uuid4())
    async_task_id = str(uuid.uuid4())

    # Create AsyncTask
    async_task = AsyncTask(
        id=async_task_id,
        celery_task_id="celery-task-123",
        task_type="evaluation",
        entity_id=evaluation_id,
        user_id=test_user_id,
        status="pending",
    )
    test_db_session.add(async_task)

    # Create Evaluation
    evaluation = Evaluation(
        id=evaluation_id,
        user_id=test_user_id,
        status="pending",
        strategy_names=["strategy_a", "strategy_b"],
        problem_ids=["problem_1", "problem_2"],
        problem_count=2,
        api_key_id="key-123",
        budget_cap_usd=100.0,
        async_task_id=async_task_id,
    )
    test_db_session.add(evaluation)
    test_db_session.commit()

    return {
        "evaluation": evaluation,
        "async_task": async_task,
        "evaluation_id": evaluation_id,
        "async_task_id": async_task_id,
    }


class TestProgressInfoSchema:
    """Test ProgressInfo schema changes."""

    def test_progress_info_with_all_fields(self):
        """Verify ProgressInfo can be created with all fields."""
        progress = ProgressInfo(
            current=5,
            total=10,
            message="Processing problems...",
        )
        assert progress.current == 5
        assert progress.total == 10
        assert progress.message == "Processing problems..."

    def test_progress_info_with_optional_message(self):
        """Verify message field is optional."""
        progress = ProgressInfo(
            current=5,
            total=10,
        )
        assert progress.current == 5
        assert progress.total == 10
        assert progress.message is None

    def test_progress_info_json_serialization(self):
        """Verify ProgressInfo can be JSON serialized."""
        progress = ProgressInfo(current=5, total=10, message="Test")
        data = progress.model_dump(exclude_none=True)
        assert data == {"current": 5, "total": 10, "message": "Test"}


class TestEvaluationResponseSchema:
    """Test EvaluationResponse schema changes."""

    def test_evaluation_response_with_progress(self):
        """Verify EvaluationResponse can include progress info."""
        response = EvaluationResponse(
            evaluation_id="eval-123",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            status="running",
            can_start=False,
            can_cancel=True,
            execution_progress=ExecutionProgress(
                completed_units=5, total_units=10, percentage=50.0
            ),
            strategy_names=["strategy_a"],
            problem_count=10,
            spent_usd=0.0,
            budget_cap_usd=100.0,
            progress=ProgressInfo(current=5, total=10, message="Running..."),
        )
        assert response.progress is not None
        assert response.progress.current == 5
        assert response.progress.total == 10

    def test_evaluation_response_without_progress(self):
        """Verify progress field is optional."""
        response = EvaluationResponse(
            evaluation_id="eval-123",
            created_at="2024-01-01T00:00:00Z",
            updated_at="2024-01-01T00:00:00Z",
            status="pending",
            can_start=True,
            can_cancel=False,
            execution_progress=ExecutionProgress(completed_units=0, total_units=10, percentage=0.0),
            strategy_names=["strategy_a"],
            problem_count=10,
            spent_usd=0.0,
            budget_cap_usd=100.0,
        )
        assert response.progress is None


class TestCreateEvaluationWithAsyncTask:
    """Test create_evaluation method with Celery task submission."""

    def test_create_evaluation_submits_celery_task(
        self, test_db_session, test_user_id, create_request
    ):
        """Verify create_evaluation submits a Celery task."""
        from api.services.evaluation_service import EvaluationService

        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            # Mock Celery task submission
            mock_result = Mock()
            mock_result.id = "celery-task-123"
            mock_send_task.return_value = mock_result

            # Create service with the test session
            service = EvaluationService.__new__(EvaluationService)
            service._session_factory = lambda: test_db_session

            # When: Create evaluation
            response = service.create_evaluation_async(create_request, test_user_id)

        # Then: Response is valid EvaluationResponse
        assert isinstance(response, EvaluationResponse)
        assert response.status == "pending"
        assert response.strategy_names == ["strategy_a", "strategy_b"]
        assert response.problem_count == 3

    def test_create_evaluation_creates_async_task(
        self, test_db_session, test_user_id, create_request
    ):
        """Verify create_evaluation creates an AsyncTask record."""
        from api.services.evaluation_service import EvaluationService

        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-123"
            mock_send_task.return_value = mock_result

            service = EvaluationService.__new__(EvaluationService)
            service._session_factory = lambda: test_db_session

            # When: Create evaluation
            response = service.create_evaluation_async(create_request, test_user_id)

        # Then: AsyncTask should be created
        async_tasks = test_db_session.query(AsyncTask).all()
        assert len(async_tasks) > 0

    def test_create_evaluation_links_evaluation_to_task(
        self, test_db_session, test_user_id, create_request
    ):
        """Verify Evaluation is linked to AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-123"
            mock_send_task.return_value = mock_result

            service = EvaluationService.__new__(EvaluationService)
            service._session_factory = lambda: test_db_session

            # When: Create evaluation
            response = service.create_evaluation_async(create_request, test_user_id)

        # Then: Evaluation should have async_task_id
        evaluation = test_db_session.query(Evaluation).filter_by(user_id=test_user_id).first()
        assert evaluation is not None
        assert evaluation.async_task_id is not None


class TestGetEvaluationAggregatesStatus:
    """Test get_evaluation method aggregates AsyncTask status."""

    def test_get_evaluation_returns_pending_status(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify get_evaluation returns pending status from AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # When: Get evaluation
        response = service.get_evaluation_async(evaluation_with_task["evaluation_id"], test_user_id)

        # Then: Status should be from AsyncTask
        assert response.status == "pending"

    def test_get_evaluation_returns_running_status(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify get_evaluation returns running status from AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Update AsyncTask to running
        evaluation_with_task["async_task"].status = "running"
        test_db_session.commit()

        # When: Get evaluation
        response = service.get_evaluation_async(evaluation_with_task["evaluation_id"], test_user_id)

        # Then: Status should be running
        assert response.status == "running"

    def test_get_evaluation_includes_progress_from_async_task(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify get_evaluation includes progress info from AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Update AsyncTask with progress
        evaluation_with_task["async_task"].status = "running"
        evaluation_with_task["async_task"].progress = {
            "current": 5,
            "total": 10,
            "message": "Processing...",
        }
        test_db_session.commit()

        # When: Get evaluation
        response = service.get_evaluation_async(evaluation_with_task["evaluation_id"], test_user_id)

        # Then: Progress should be included
        assert response.progress is not None
        assert response.progress.current == 5
        assert response.progress.total == 10
        assert response.progress.message == "Processing..."


class TestPauseEvaluation:
    """Test pause_evaluation method."""

    def test_pause_evaluation_pauses_running_task(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify pause_evaluation pauses a running task."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Update AsyncTask to running
        evaluation_with_task["async_task"].status = "running"
        test_db_session.commit()

        # Mock TaskManager entirely to avoid any Celery calls
        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr

            # Mock the pause_task to return the updated async task
            paused_task = evaluation_with_task["async_task"]
            paused_task.status = "paused"
            mock_task_mgr.pause_task.return_value = paused_task

            # When: Pause evaluation
            response = service.pause_evaluation(evaluation_with_task["evaluation_id"], test_user_id)

        # Then: Task should be paused in response
        assert response.status == "paused"

    def test_pause_evaluation_fails_for_non_running_task(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify pause_evaluation fails if task is not running."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Mock TaskManager to raise error
        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr
            mock_task_mgr.pause_task.side_effect = ValueError("Can only pause running")

            # When/Then: Pause evaluation should fail (task is pending, not running)
            with pytest.raises(ValueError, match="Can only pause running"):
                service.pause_evaluation(evaluation_with_task["evaluation_id"], test_user_id)

    def test_pause_evaluation_fails_if_no_async_task(self, test_db_session, test_user_id):
        """Verify pause_evaluation fails if evaluation has no AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Create evaluation without async task
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            user_id=test_user_id,
            status="pending",
            strategy_names=["strategy_a"],
            problem_ids=["problem_1"],
            problem_count=1,
        )
        test_db_session.add(evaluation)
        test_db_session.commit()

        # When/Then: Pause should fail
        with pytest.raises(ValueError, match="no associated task"):
            service.pause_evaluation(evaluation.id, test_user_id)


class TestResumeEvaluation:
    """Test resume_evaluation method."""

    def test_resume_evaluation_creates_new_task(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify resume_evaluation creates a new task."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Update AsyncTask to paused
        evaluation_with_task["async_task"].status = "paused"
        test_db_session.commit()

        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr

            # Mock get_task and create_task
            mock_task_mgr.get_task.return_value = evaluation_with_task["async_task"]

            new_async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id="celery-task-new",
                task_type="evaluation",
                entity_id=evaluation_with_task["evaluation_id"],
                user_id=test_user_id,
                status="pending",
            )
            # Add the new task to the test session so it persists
            test_db_session.add(new_async_task)
            test_db_session.commit()

            mock_task_mgr.create_task.return_value = new_async_task

            # When: Resume evaluation
            response = service.resume_evaluation(
                evaluation_with_task["evaluation_id"], test_user_id
            )

        # Then: Evaluation should link to new task
        evaluation = (
            test_db_session.query(Evaluation)
            .filter_by(id=evaluation_with_task["evaluation_id"])
            .first()
        )
        assert evaluation.async_task_id == new_async_task.id

    def test_resume_evaluation_updates_evaluation_status(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify resume_evaluation updates evaluation status to pending."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # Update AsyncTask to paused, evaluation to paused
        evaluation_with_task["async_task"].status = "paused"
        evaluation_with_task["evaluation"].status = "paused"
        test_db_session.commit()

        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr

            # Mock get_task and create_task
            mock_task_mgr.get_task.return_value = evaluation_with_task["async_task"]

            new_async_task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id="celery-task-new",
                task_type="evaluation",
                entity_id=evaluation_with_task["evaluation_id"],
                user_id=test_user_id,
                status="pending",
            )
            mock_task_mgr.create_task.return_value = new_async_task

            # When: Resume evaluation
            response = service.resume_evaluation(
                evaluation_with_task["evaluation_id"], test_user_id
            )

        # Then: Evaluation status should be pending
        evaluation = (
            test_db_session.query(Evaluation)
            .filter_by(id=evaluation_with_task["evaluation_id"])
            .first()
        )
        assert evaluation.status == "pending"


class TestDeleteEvaluation:
    """Test delete_evaluation method with task cancellation."""

    def test_delete_evaluation_cancels_async_task(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify delete_evaluation cancels the associated AsyncTask."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr

            # When: Delete evaluation
            service.delete_evaluation_async(evaluation_with_task["evaluation_id"], test_user_id)

        # Then: cancel_task should have been called
        mock_task_mgr.cancel_task.assert_called_once()

    def test_delete_evaluation_removes_evaluation_record(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify delete_evaluation removes the evaluation record."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        evaluation_id = evaluation_with_task["evaluation_id"]

        with patch("api.services.evaluation_service.TaskManager") as MockTaskManager:
            mock_task_mgr = Mock()
            MockTaskManager.return_value = mock_task_mgr

            # When: Delete evaluation
            service.delete_evaluation_async(evaluation_id, test_user_id)

        # Then: Evaluation should be deleted
        evaluation = test_db_session.query(Evaluation).filter_by(id=evaluation_id).first()
        assert evaluation is None

    def test_delete_evaluation_fails_for_non_existent_evaluation(
        self, test_db_session, test_user_id
    ):
        """Verify delete_evaluation fails if evaluation not found."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # When/Then: Delete should fail
        with pytest.raises(ValueError, match="not found"):
            service.delete_evaluation_async("non-existent-id", test_user_id)


class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_get_evaluation_fails_for_non_existent_evaluation(self, test_db_session, test_user_id):
        """Verify get_evaluation raises error for non-existent evaluation."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # When/Then: Get should fail
        with pytest.raises(ValueError, match="not found"):
            service.get_evaluation_async("non-existent-id", test_user_id)

    def test_get_evaluation_fails_for_wrong_user(
        self, test_db_session, test_user_id, evaluation_with_task
    ):
        """Verify get_evaluation fails if user is not the owner."""
        from api.services.evaluation_service import EvaluationService

        service = EvaluationService.__new__(EvaluationService)
        service._session_factory = lambda: test_db_session

        # When/Then: Get should fail for different user
        with pytest.raises(ValueError, match="not found"):
            service.get_evaluation_async(evaluation_with_task["evaluation_id"], "different-user")


class TestEvaluationModelPersistence:
    """Task 2: EvaluationCreateRequest.model 必填且两条创建路径均持久化。

    使用真实 EvaluationService + 临时 SQLite（与生产一致的 expire_on_commit=False），
    避免共享内存 session 在同步路径 close 后触发 DetachedInstanceError。
    """

    def _service(self, tmp_path):
        from api.services.evaluation_service import EvaluationService

        return EvaluationService(f"sqlite:///{tmp_path / 'biz.sqlite3'}")

    def _request(self, **overrides):
        payload = {
            "strategy_names": ["vanilla"],
            "problem_ids": ["p1"],
            "api_key_id": "key-123",
            "model": "gpt-4o-mini",
        }
        payload.update(overrides)
        return EvaluationCreateRequest(**payload)

    def test_create_evaluation_persists_model(self, tmp_path):
        """同步 create_evaluation 回读 model 并落库 evaluations.model。"""
        service = self._service(tmp_path)

        response = service.create_evaluation(self._request(), "alice")

        assert response.model == "gpt-4o-mini"
        # 从 DB 回读确认真正持久化
        fetched = service.get_evaluation(response.evaluation_id, "alice")
        assert fetched.model == "gpt-4o-mini"

    def test_create_evaluation_async_persists_model(self, tmp_path):
        """异步 create_evaluation_async 回读 model 并落库 evaluations.model。"""
        service = self._service(tmp_path)

        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-123"
            mock_send_task.return_value = mock_result

            response = service.create_evaluation_async(self._request(), "alice")

        assert response.model == "gpt-4o-mini"
        fetched = service.get_evaluation_async(response.evaluation_id, "alice")
        assert fetched.model == "gpt-4o-mini"

    def test_create_evaluation_requires_model(self):
        """缺少 model 的创建请求应触发 Pydantic 校验失败。"""
        with pytest.raises(ValidationError):
            EvaluationCreateRequest(
                strategy_names=["vanilla"],
                problem_ids=["p1"],
                api_key_id="key-123",
            )

    def test_create_evaluation_rejects_empty_model(self):
        """model 为空字符串应触发 min_length 校验失败。"""
        with pytest.raises(ValidationError):
            EvaluationCreateRequest(
                strategy_names=["vanilla"],
                problem_ids=["p1"],
                api_key_id="key-123",
                model="",
            )
