"""
TaskManager 单元测试

测试异步任务管理器的核心功能，包括创建、查询、更新、暂停和取消任务。
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Evaluation
from src.task_manager import TaskManager
from src.task_service import TaskService, TaskUnit


@pytest.fixture
def db_session():
    """创建内存数据库会话用于测试。"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()


@pytest.fixture
def task_manager(db_session):
    """创建 TaskManager 实例。"""
    return TaskManager(db_session)


class TestCreateTask:
    """测试创建任务功能"""

    def test_create_task(self, task_manager, db_session):
        """验证创建任务并提交到 Celery"""
        # Given: 任务参数
        task_type = "evaluation"
        entity_id = str(uuid.uuid4())
        user_id = "user123"
        celery_task_name = "src.tasks.evaluation.run_evaluation_task"

        # Mock Celery apply_async
        with patch("src.task_manager.celery_app.send_task") as mock_send_task:
            mock_result = Mock()
            mock_result.id = "celery-task-id-123"
            mock_send_task.return_value = mock_result

            # When: 创建任务
            task = task_manager.create_task(
                task_type=task_type,
                entity_id=entity_id,
                user_id=user_id,
                celery_task_name=celery_task_name,
                celery_task_args=(entity_id,),
                celery_task_kwargs={"user_id": user_id},
            )

        # Then: 任务已创建并保存到数据库
        assert task.id is not None
        assert task.task_type == task_type
        assert task.entity_id == entity_id
        assert task.user_id == user_id
        assert task.status == "pending"
        assert task.celery_task_id == "celery-task-id-123"

        # 验证数据库记录
        db_task = db_session.query(AsyncTask).filter_by(id=task.id).first()
        assert db_task is not None
        assert db_task.celery_task_id == "celery-task-id-123"


class TestEnqueueTask:
    """测试先落库后发布的入队时序"""

    def test_enqueue_commits_before_publish(self, task_manager, db_session):
        """验证关联在发布前已落库、on_before_publish 先于 send_task 执行"""
        entity_id = str(uuid.uuid4())
        events = []
        seen = {}

        def on_before_publish(async_task):
            # 钩子执行时发布尚未发生
            events.append("hook")
            seen["celery_task_id"] = async_task.celery_task_id

        def send_side_effect(*args, **kwargs):
            events.append("send")
            # 发布时记录已提交：expire 后仍能从数据库查回
            db_session.expire_all()
            committed = (
                db_session.query(AsyncTask).filter_by(celery_task_id=kwargs["task_id"]).first()
            )
            seen["committed"] = committed is not None
            return Mock()

        with patch(
            "src.task_manager.celery_app.send_task", side_effect=send_side_effect
        ) as mock_send:
            task = task_manager.enqueue_task(
                task_type="evaluation",
                entity_id=entity_id,
                user_id="user123",
                celery_task_name="src.tasks.evaluation.run_evaluation_task",
                celery_task_args=(entity_id,),
                on_before_publish=on_before_publish,
            )

        assert events == ["hook", "send"]
        assert seen["committed"] is True
        assert task.celery_task_id == seen["celery_task_id"]
        mock_send.assert_called_once()

    def test_enqueue_publishes_with_pregenerated_id(self, task_manager, db_session):
        """验证发布使用预生成的 celery_task_id，并与落库记录一致"""
        entity_id = str(uuid.uuid4())

        with patch("src.task_manager.celery_app.send_task", return_value=Mock()) as mock_send:
            task = task_manager.enqueue_task(
                task_type="evaluation",
                entity_id=entity_id,
                user_id="user123",
                celery_task_name="src.tasks.evaluation.run_evaluation_task",
                celery_task_args=(entity_id,),
            )

        _, kwargs = mock_send.call_args
        assert kwargs["task_id"] == task.celery_task_id
        assert task.celery_task_id != ""
        db_task = db_session.query(AsyncTask).filter_by(id=task.id).first()
        assert db_task.celery_task_id == task.celery_task_id

    def test_enqueue_marks_failed_when_publish_raises(self, task_manager, db_session):
        """验证 send_task 失败时任务置为 failed 并原样抛出"""
        entity_id = str(uuid.uuid4())
        boom = RuntimeError("broker unavailable")

        with patch("src.task_manager.celery_app.send_task", side_effect=boom):
            with pytest.raises(RuntimeError, match="broker unavailable"):
                task_manager.enqueue_task(
                    task_type="evaluation",
                    entity_id=entity_id,
                    user_id="user123",
                    celery_task_name="src.tasks.evaluation.run_evaluation_task",
                    celery_task_args=(entity_id,),
                )

        db_session.expire_all()
        failed = db_session.query(AsyncTask).filter_by(entity_id=entity_id).first()
        assert failed is not None
        assert failed.status == "failed"
        assert failed.error_message == "failed to publish task to broker"
        assert failed.completed_at is not None


class TestGetTask:
    """测试获取任务功能"""

    def test_get_task(self, task_manager, db_session):
        """验证获取任务基本功能"""
        # Given: 数据库中存在一个任务
        task_id = str(uuid.uuid4())
        user_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="completed",  # 使用 completed 状态避免同步 Celery
        )
        db_session.add(task)
        db_session.commit()

        # When: 获取任务
        result = task_manager.get_task(task_id)

        # Then: 返回正确的任务
        assert result.id == task_id
        assert result.user_id == user_id
        assert result.status == "completed"

    def test_get_task_with_user_id_authorization(self, task_manager, db_session):
        """验证用户权限验证"""
        # Given: 数据库中存在一个任务
        task_id = str(uuid.uuid4())
        owner_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=owner_id,
            status="completed",  # 使用 completed 状态避免同步 Celery
        )
        db_session.add(task)
        db_session.commit()

        # When/Then: 使用正确的 user_id 可以获取
        result = task_manager.get_task(task_id, user_id=owner_id)
        assert result.id == task_id

        # When/Then: 使用错误的 user_id 抛出异常
        with pytest.raises(ValueError, match="Task not found or access denied"):
            task_manager.get_task(task_id, user_id="wrong_user")

    def test_get_task_not_found(self, task_manager):
        """验证任务不存在时抛出异常"""
        # When/Then: 获取不存在的任务
        with pytest.raises(ValueError, match="Task not found"):
            task_manager.get_task("nonexistent-task-id")

    def test_get_task_with_celery_sync(self, task_manager, db_session):
        """验证获取任务时同步 Celery 状态"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user123",
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # Mock Celery AsyncResult
        with patch("src.task_manager.celery_app.AsyncResult") as mock_async_result:
            mock_result = Mock()
            mock_result.state = "PROGRESS"
            mock_result.info = {"current": 50, "total": 100}
            mock_async_result.return_value = mock_result

            # When: 获取任务
            result = task_manager.get_task(task_id)

            # Then: 状态已同步
            assert result.status == "running"
            assert result.progress == {"current": 50, "total": 100}


class TestUpdateTaskProgress:
    """测试更新任务进度功能"""

    def test_update_task_progress(self, task_manager, db_session):
        """验证更新任务进度和状态"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user123",
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # When: 更新进度
        progress_data = {"current": 50, "total": 100, "message": "Processing..."}
        task_manager.update_task_progress(task_id, progress_data, "running")

        # Then: 进度已更新
        updated_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
        assert updated_task.progress == progress_data
        assert updated_task.status == "running"


class TestUpdateTaskStatus:
    """测试更新任务状态功能"""

    def test_update_task_status(self, task_manager, db_session):
        """验证更新任务状态"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user123",
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # When: 更新为 completed 状态
        task_manager.update_task_status(task_id, "completed")

        # Then: 状态已更新，completed_at 已设置
        updated_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
        assert updated_task.status == "completed"
        assert updated_task.completed_at is not None

    def test_update_task_status_with_error(self, task_manager, db_session):
        """验证更新任务状态并记录错误信息"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user123",
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # When: 更新为 failed 状态并记录错误
        error_msg = "Database connection failed"
        task_manager.update_task_status(task_id, "failed", error_message=error_msg)

        # Then: 状态和错误信息已更新
        updated_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
        assert updated_task.status == "failed"
        assert updated_task.error_message == error_msg
        assert updated_task.completed_at is not None


class TestPauseTask:
    """测试暂停任务功能"""

    def test_pause_task(self, task_manager, db_session):
        """验证暂停运行中的任务"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        user_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # Mock Celery state sync to avoid Redis connection
        with patch.object(task_manager, "_sync_celery_state"):
            # When: 暂停任务
            result = task_manager.pause_task(task_id, user_id)

            # Then: 任务状态变为 paused
            assert result.status == "paused"
            db_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
            assert db_task.status == "paused"

    def test_pause_task_invalid_status(self, task_manager, db_session):
        """验证只能暂停运行中的任务"""
        # Given: 数据库中存在一个已完成的任务
        task_id = str(uuid.uuid4())
        user_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="completed",
        )
        db_session.add(task)
        db_session.commit()

        # When/Then: 暂停已完成的任务应抛出异常
        with pytest.raises(ValueError, match="Can only pause running tasks"):
            task_manager.pause_task(task_id, user_id)


class TestCancelTask:
    """测试取消任务功能"""

    def test_cancel_task(self, task_manager, db_session):
        """验证取消未完成的任务"""
        # Given: 数据库中存在一个运行中的任务
        task_id = str(uuid.uuid4())
        user_id = "user123"
        celery_task_id = "celery-123"
        task = AsyncTask(
            id=task_id,
            celery_task_id=celery_task_id,
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="running",
        )
        db_session.add(task)
        db_session.commit()

        # Mock Celery revoke and state sync
        with (
            patch("src.task_manager.celery_app.control.revoke") as mock_revoke,
            patch.object(task_manager, "_sync_celery_state"),
        ):
            # When: 取消任务
            result = task_manager.cancel_task(task_id, user_id)

            # Then: 任务状态变为 cancelled，Celery 任务被 revoke
            assert result.status == "cancelled"
            mock_revoke.assert_called_once_with(celery_task_id, terminate=True)

            db_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
            assert db_task.status == "cancelled"

    def test_cancel_running_evaluation_requests_checkpoint_cancel(
        self, task_manager, db_session, tmp_path, monkeypatch
    ):
        """运行中的评估取消会把同一检查点标为请求取消。"""
        monkeypatch.chdir(tmp_path)
        evaluation_id = str(uuid.uuid4())
        task_id = str(uuid.uuid4())
        user_id = "user123"
        run_id = f"eval-{evaluation_id}"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=evaluation_id,
            user_id=user_id,
            status="running",
        )
        db_session.add(task)
        db_session.commit()
        service = TaskService(root=f"data/tasks/{evaluation_id}")
        service.create(
            units=[
                TaskUnit(unit_id="u1", strategy="vanilla", problem_id="p1"),
                TaskUnit(unit_id="u2", strategy="vanilla", problem_id="p2"),
            ],
            config_fingerprint="cfg",
            dataset_fingerprint="data",
            run_id=run_id,
        )

        with (
            patch("src.task_manager.celery_app.control.revoke"),
            patch.object(task_manager, "_sync_celery_state"),
        ):
            result = task_manager.cancel_task(task_id, user_id)

        assert result.status == "cancelled"
        assert service.get(run_id).cancel_requested is True

    def test_cancel_evaluation_without_checkpoint_still_cancels(
        self, task_manager, db_session, tmp_path, monkeypatch
    ):
        """检查点尚未生成时，取消仍 revoke 并把任务写成 cancelled。"""
        monkeypatch.chdir(tmp_path)
        task_id = str(uuid.uuid4())
        user_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-456",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="pending",
        )
        db_session.add(task)
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.control.revoke") as mock_revoke,
            patch.object(task_manager, "_sync_celery_state"),
        ):
            result = task_manager.cancel_task(task_id, user_id)

        assert result.status == "cancelled"
        mock_revoke.assert_called_once_with("celery-456", terminate=True)

    def test_cancel_task_already_completed(self, task_manager, db_session):
        """验证不能取消已完成的任务"""
        # Given: 数据库中存在一个已完成的任务
        task_id = str(uuid.uuid4())
        user_id = "user123"
        task = AsyncTask(
            id=task_id,
            celery_task_id="celery-123",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="completed",
        )
        db_session.add(task)
        db_session.commit()

        # When/Then: 取消已完成的任务应抛出异常
        with pytest.raises(ValueError, match="Cannot cancel completed or failed tasks"):
            task_manager.cancel_task(task_id, user_id)


class TestListTasks:
    """测试任务列表功能"""

    def test_list_tasks(self, task_manager, db_session):
        """验证列出用户任务"""
        # Given: 数据库中存在多个任务
        user_id = "user123"
        task1 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="celery-1",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="completed",
        )
        task2 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="celery-2",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="running",
        )
        task3 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="celery-3",
            task_type="import",
            entity_id=str(uuid.uuid4()),
            user_id="other_user",
            status="pending",
        )
        db_session.add_all([task1, task2, task3])
        db_session.commit()

        # When: 列出用户任务
        tasks, total = task_manager.list_tasks(user_id=user_id)

        # Then: 返回该用户的任务
        assert total == 2
        assert len(tasks) == 2
        task_ids = {t.id for t in tasks}
        assert task1.id in task_ids
        assert task2.id in task_ids
        assert task3.id not in task_ids

    def test_list_tasks_with_filters(self, task_manager, db_session):
        """验证任务列表过滤功能"""
        # Given: 数据库中存在多个不同类型和状态的任务
        user_id = "user123"
        tasks = [
            AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-{i}",
                task_type="evaluation" if i % 2 == 0 else "import",
                entity_id=str(uuid.uuid4()),
                user_id=user_id,
                status="running" if i % 3 == 0 else "completed",
            )
            for i in range(6)
        ]
        db_session.add_all(tasks)
        db_session.commit()

        # When: 按 task_type 过滤
        eval_tasks, eval_total = task_manager.list_tasks(user_id=user_id, task_type="evaluation")

        # Then: 只返回 evaluation 类型的任务
        assert eval_total == 3
        assert all(t.task_type == "evaluation" for t in eval_tasks)

        # When: 按 status 过滤
        running_tasks, running_total = task_manager.list_tasks(user_id=user_id, status="running")

        # Then: 只返回 running 状态的任务
        assert running_total == 2
        assert all(t.status == "running" for t in running_tasks)

    def test_list_tasks_pagination(self, task_manager, db_session):
        """验证任务列表分页功能"""
        # Given: 数据库中存在多个任务
        user_id = "user123"
        tasks = [
            AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=f"celery-{i}",
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=user_id,
                status="completed",
            )
            for i in range(10)
        ]
        db_session.add_all(tasks)
        db_session.commit()

        # When: 分页查询
        page1_tasks, total = task_manager.list_tasks(user_id=user_id, limit=5, offset=0)
        page2_tasks, _ = task_manager.list_tasks(user_id=user_id, limit=5, offset=5)

        # Then: 正确分页
        assert total == 10
        assert len(page1_tasks) == 5
        assert len(page2_tasks) == 5
        # 确保没有重复
        page1_ids = {t.id for t in page1_tasks}
        page2_ids = {t.id for t in page2_tasks}
        assert len(page1_ids & page2_ids) == 0


def _paused_evaluation(db_session, user_id="user123", task_type="evaluation", status="paused"):
    task_id = str(uuid.uuid4())
    entity_id = str(uuid.uuid4())
    task = AsyncTask(
        id=task_id,
        celery_task_id=f"celery-{task_id}",
        task_type=task_type,
        entity_id=entity_id,
        user_id=user_id,
        status=status,
    )
    db_session.add(task)
    if task_type == "evaluation":
        db_session.add(
            Evaluation(
                id=entity_id,
                user_id=user_id,
                status="paused",
                strategy_names=["vanilla"],
                problem_ids=["p1"],
                problem_count=1,
                async_task_id=task_id,
            )
        )
    db_session.commit()
    return task


class TestResumeTask:
    """测试恢复已暂停的评估任务。"""

    def test_resume_paused_evaluation_requeues_same_task(self, task_manager, db_session):
        task = _paused_evaluation(db_session)
        original_celery_id = task.celery_task_id
        published = {}

        def send_side_effect(*args, **kwargs):
            db_session.expire_all()
            row = db_session.query(AsyncTask).filter_by(id=task.id).one()
            published["status_before_send"] = row.status
            published["celery_before_send"] = row.celery_task_id
            return Mock()

        with patch(
            "src.task_manager.celery_app.send_task", side_effect=send_side_effect
        ) as mock_send:
            result = task_manager.resume_task(task.id, task.user_id)

        assert result.id == task.id
        assert result.status == "pending"
        assert result.celery_task_id != original_celery_id
        assert published["status_before_send"] == "pending"
        assert published["celery_before_send"] == result.celery_task_id
        mock_send.assert_called_once_with(
            "src.tasks.evaluation.run_evaluation_task",
            args=(task.entity_id,),
            task_id=result.celery_task_id,
        )
        evaluation = db_session.query(Evaluation).filter_by(id=task.entity_id).one()
        assert evaluation.status == "pending"
        assert evaluation.async_task_id == task.id

    def test_resume_marks_failed_when_publish_raises(self, task_manager, db_session):
        task = _paused_evaluation(db_session)

        with patch(
            "src.task_manager.celery_app.send_task", side_effect=RuntimeError("broker down")
        ):
            with pytest.raises(RuntimeError, match="broker down"):
                task_manager.resume_task(task.id, task.user_id)

        db_session.expire_all()
        row = db_session.query(AsyncTask).filter_by(id=task.id).one()
        assert row.status == "failed"
        assert row.error_message == "failed to publish task to broker"
        assert row.completed_at is not None

    @pytest.mark.parametrize("status", ["pending", "running", "completed", "failed", "cancelled"])
    def test_resume_rejects_non_paused_without_publish(self, task_manager, db_session, status):
        task = _paused_evaluation(db_session, status=status)
        original_celery_id = task.celery_task_id

        with (
            patch("src.task_manager.celery_app.AsyncResult"),
            patch("src.task_manager.celery_app.send_task") as mock_send,
            pytest.raises(ValueError, match="Can only resume paused tasks"),
        ):
            task_manager.resume_task(task.id, task.user_id)

        mock_send.assert_not_called()
        db_session.expire_all()
        row = db_session.query(AsyncTask).filter_by(id=task.id).one()
        assert row.status == status
        assert row.celery_task_id == original_celery_id

    @pytest.mark.parametrize(
        "task_type", ["experiment", "import", "benchmark", "ab_test", "unknown"]
    )
    def test_resume_rejects_non_evaluation_without_publish(
        self, task_manager, db_session, task_type
    ):
        task = _paused_evaluation(db_session, task_type=task_type)
        original_celery_id = task.celery_task_id

        with (
            patch("src.task_manager.celery_app.send_task") as mock_send,
            pytest.raises(ValueError, match="not linked|Unsupported"),
        ):
            task_manager.resume_task(task.id, task.user_id)

        mock_send.assert_not_called()
        db_session.expire_all()
        row = db_session.query(AsyncTask).filter_by(id=task.id).one()
        assert row.status == "paused"
        assert row.celery_task_id == original_celery_id

    def test_resume_rejects_other_users_task(self, task_manager, db_session):
        task = _paused_evaluation(db_session, user_id="owner")

        with (
            patch("src.task_manager.celery_app.send_task") as mock_send,
            pytest.raises(ValueError, match="not found or access denied"),
        ):
            task_manager.resume_task(task.id, "intruder")

        mock_send.assert_not_called()
        db_session.expire_all()
        row = db_session.query(AsyncTask).filter_by(id=task.id).one()
        assert row.status == "paused"

    def test_resume_rejects_unlinked_evaluation_without_publish(self, task_manager, db_session):
        task = _paused_evaluation(db_session)
        evaluation = db_session.query(Evaluation).filter_by(id=task.entity_id).one()
        evaluation.async_task_id = None
        db_session.commit()

        with (
            patch("src.task_manager.celery_app.send_task") as mock_send,
            pytest.raises(ValueError, match="not linked"),
        ):
            task_manager.resume_task(task.id, task.user_id)

        mock_send.assert_not_called()
        db_session.expire_all()
        row = db_session.query(AsyncTask).filter_by(id=task.id).one()
        assert row.status == "paused"


@pytest.mark.parametrize("progress", [False, True])
def test_execution_timestamps_survive_duplicates_and_reset_end_on_retry(
    db_session, task_manager, progress
):
    from datetime import datetime

    task = AsyncTask(
        id="timing", celery_task_id="timing", task_type="evaluation", entity_id="e", user_id="u"
    )
    db_session.add(task)
    db_session.commit()

    def transition(status):
        if progress:
            task_manager.update_task_progress(task.id, {"current": 0}, status)
        else:
            task_manager.update_task_status(task.id, status)

    transition("running")
    assert task.started_at is not None
    first = datetime(2026, 1, 1)
    task.started_at = first
    db_session.commit()
    transition("running")
    assert task.started_at == first
    transition("failed")
    assert task.completed_at is not None
    end = task.completed_at
    transition("failed")
    assert task.completed_at == end
    transition("running")
    assert task.started_at == first and task.completed_at is None
    transition("completed")
    assert task.completed_at is not None
