"""
TaskManager 单元测试

测试异步任务管理器的核心功能，包括创建、查询、更新、暂停和取消任务。
"""

import uuid
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import AsyncTask, Base
from src.task_manager import TaskManager


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
                celery_task_kwargs={"user_id": user_id}
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
            status="completed"  # 使用 completed 状态避免同步 Celery
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
            status="completed"  # 使用 completed 状态避免同步 Celery
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
            status="running"
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
            status="running"
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
            status="running"
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
            status="running"
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
            status="running"
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
            status="completed"
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
            status="running"
        )
        db_session.add(task)
        db_session.commit()

        # Mock Celery revoke and state sync
        with patch("src.task_manager.celery_app.control.revoke") as mock_revoke, \
             patch.object(task_manager, "_sync_celery_state"):
            # When: 取消任务
            result = task_manager.cancel_task(task_id, user_id)

            # Then: 任务状态变为 cancelled，Celery 任务被 revoke
            assert result.status == "cancelled"
            mock_revoke.assert_called_once_with(celery_task_id, terminate=True)

            db_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
            assert db_task.status == "cancelled"

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
            status="completed"
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
            status="completed"
        )
        task2 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="celery-2",
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id=user_id,
            status="running"
        )
        task3 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="celery-3",
            task_type="import",
            entity_id=str(uuid.uuid4()),
            user_id="other_user",
            status="pending"
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
                status="running" if i % 3 == 0 else "completed"
            )
            for i in range(6)
        ]
        db_session.add_all(tasks)
        db_session.commit()

        # When: 按 task_type 过滤
        eval_tasks, eval_total = task_manager.list_tasks(
            user_id=user_id,
            task_type="evaluation"
        )

        # Then: 只返回 evaluation 类型的任务
        assert eval_total == 3
        assert all(t.task_type == "evaluation" for t in eval_tasks)

        # When: 按 status 过滤
        running_tasks, running_total = task_manager.list_tasks(
            user_id=user_id,
            status="running"
        )

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
                status="completed"
            )
            for i in range(10)
        ]
        db_session.add_all(tasks)
        db_session.commit()

        # When: 分页查询
        page1_tasks, total = task_manager.list_tasks(
            user_id=user_id,
            limit=5,
            offset=0
        )
        page2_tasks, _ = task_manager.list_tasks(
            user_id=user_id,
            limit=5,
            offset=5
        )

        # Then: 正确分页
        assert total == 10
        assert len(page1_tasks) == 5
        assert len(page2_tasks) == 5
        # 确保没有重复
        page1_ids = {t.id for t in page1_tasks}
        page2_ids = {t.id for t in page2_tasks}
        assert len(page1_ids & page2_ids) == 0
