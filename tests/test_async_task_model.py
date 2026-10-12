"""AsyncTask 模型单元测试 (Task 2)。

测试 AsyncTask 模型的基本功能：创建、查询、状态管理和与 Evaluation 的关联。
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from api.db import Base, run_migrations
from api.db.models import AsyncTask, Evaluation


@pytest.fixture
def db_session(tmp_path):
    """创建临时数据库会话用于测试。"""
    url = f"sqlite:///{tmp_path / 'test_async_task.sqlite3'}"
    run_migrations(url)
    engine = create_engine(url)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


class TestAsyncTaskModel:
    """测试 AsyncTask 模型的基本功能。"""

    def test_create_async_task_with_required_fields(self, db_session):
        """测试使用必需字段创建 AsyncTask。"""
        task_id = str(uuid.uuid4())
        celery_id = str(uuid.uuid4())

        task = AsyncTask(
            id=task_id,
            celery_task_id=celery_id,
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user123",
            status="pending"
        )

        db_session.add(task)
        db_session.commit()

        # 验证任务已保存
        saved_task = db_session.query(AsyncTask).filter_by(id=task_id).first()
        assert saved_task is not None
        assert saved_task.celery_task_id == celery_id
        assert saved_task.task_type == "evaluation"
        assert saved_task.status == "pending"
        assert saved_task.user_id == "user123"
        assert saved_task.created_at is not None
        assert saved_task.updated_at is not None

    def test_async_task_status_transitions(self, db_session):
        """测试 AsyncTask 状态转换。"""
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=str(uuid.uuid4()),
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user456",
            status="pending"
        )
        db_session.add(task)
        db_session.commit()

        # 状态转换：pending -> running
        task.status = "running"
        task.started_at = datetime.utcnow()
        db_session.commit()

        assert task.status == "running"
        assert task.started_at is not None

        # 状态转换：running -> completed
        task.status = "completed"
        task.completed_at = datetime.utcnow()
        db_session.commit()

        assert task.status == "completed"
        assert task.completed_at is not None

    def test_async_task_progress_json_field(self, db_session):
        """测试 AsyncTask 的 progress JSON 字段。"""
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=str(uuid.uuid4()),
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user789",
            status="running",
            progress={"current": 5, "total": 10, "message": "Processing..."}
        )
        db_session.add(task)
        db_session.commit()

        saved_task = db_session.query(AsyncTask).filter_by(id=task.id).first()
        assert saved_task.progress["current"] == 5
        assert saved_task.progress["total"] == 10
        assert saved_task.progress["message"] == "Processing..."

    def test_async_task_celery_task_id_unique(self, db_session):
        """测试 celery_task_id 必须唯一。"""
        celery_id = str(uuid.uuid4())

        task1 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=celery_id,
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user1",
        )
        db_session.add(task1)
        db_session.commit()

        # 尝试创建相同 celery_task_id 的任务
        task2 = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=celery_id,  # 重复的 celery_task_id
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user2",
        )
        db_session.add(task2)

        with pytest.raises(Exception):  # SQLAlchemy 会抛出 IntegrityError
            db_session.commit()

    def test_async_task_query_by_user_id(self, db_session):
        """测试按 user_id 查询 AsyncTask。"""
        user_id = "user_query_test"

        for i in range(3):
            task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=str(uuid.uuid4()),
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id=user_id,
            )
            db_session.add(task)
        db_session.commit()

        tasks = db_session.query(AsyncTask).filter_by(user_id=user_id).all()
        assert len(tasks) == 3

    def test_async_task_query_by_status(self, db_session):
        """测试按 status 查询 AsyncTask。"""
        for status in ["pending", "running", "completed"]:
            task = AsyncTask(
                id=str(uuid.uuid4()),
                celery_task_id=str(uuid.uuid4()),
                task_type="evaluation",
                entity_id=str(uuid.uuid4()),
                user_id="user_status",
                status=status,
            )
            db_session.add(task)
        db_session.commit()

        running_tasks = db_session.query(AsyncTask).filter_by(status="running").all()
        assert len(running_tasks) == 1
        assert running_tasks[0].status == "running"

    def test_evaluation_async_task_foreign_key(self, db_session):
        """测试 Evaluation 与 AsyncTask 的外键关联。"""
        # 创建 AsyncTask
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=str(uuid.uuid4()),
            task_type="evaluation",
            entity_id=str(uuid.uuid4()),
            user_id="user_fk",
        )
        db_session.add(task)
        db_session.commit()

        # 创建关联的 Evaluation
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            user_id="user_fk",
            async_task_id=task.id,  # 外键关联
        )
        db_session.add(evaluation)
        db_session.commit()

        # 验证关联
        saved_eval = db_session.query(Evaluation).filter_by(id=evaluation.id).first()
        assert saved_eval.async_task_id == task.id

    def test_async_task_table_has_required_indexes(self, tmp_path):
        """测试 async_tasks 表具有必需的索引。"""
        url = f"sqlite:///{tmp_path / 'test_indexes.sqlite3'}"
        run_migrations(url)
        engine = create_engine(url)
        inspector = inspect(engine)

        indexes = inspector.get_indexes("async_tasks")
        index_columns = {idx["name"]: idx["column_names"] for idx in indexes}

        # 验证关键索引存在
        assert any("celery_task_id" in cols for cols in index_columns.values())
        assert any("task_type" in cols for cols in index_columns.values())
        assert any("entity_id" in cols for cols in index_columns.values())
        assert any("user_id" in cols for cols in index_columns.values())
        assert any("status" in cols for cols in index_columns.values())
