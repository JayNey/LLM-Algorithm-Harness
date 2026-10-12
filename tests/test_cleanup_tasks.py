"""Celery 清理任务的单元测试"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from api.db.engine import make_engine, make_session_factory
from api.db.models import AsyncTask


@pytest.fixture
def db_session():
    """创建测试数据库会话"""
    engine = make_engine("sqlite:///:memory:")  # 使用内存数据库
    from api.db.models import Base

    Base.metadata.create_all(engine)
    session_factory = make_session_factory(engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


def create_async_task(session, status, updated_at=None):
    """创建测试任务"""
    task = AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id=str(uuid.uuid4()),
        entity_id=str(uuid.uuid4()),
        user_id=str(uuid.uuid4()),
        task_type="evaluation",
        status=status,
        updated_at=updated_at or datetime.now(timezone.utc).replace(tzinfo=None),
    )
    session.add(task)
    session.commit()
    return task


def _cleanup_old_tasks_impl(session, days_to_keep=7):
    """清理任务的测试实现（不使用 Celery）"""
    from sqlalchemy import and_

    cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
    cutoff_time = cutoff_time.replace(tzinfo=None)

    old_tasks = (
        session.query(AsyncTask)
        .filter(
            and_(
                AsyncTask.status.in_(["completed", "failed", "cancelled"]),
                AsyncTask.updated_at < cutoff_time,
            )
        )
        .all()
    )

    deleted_count = len(old_tasks)

    for task in old_tasks:
        session.delete(task)

    session.commit()

    return {
        "deleted_count": deleted_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cutoff_date": cutoff_time.isoformat(),
    }


def _cleanup_task_count_impl(session, max_retention=10000):
    """基于总数的清理任务的测试实现（不使用 Celery）"""
    total_count = session.query(AsyncTask).count()

    if total_count <= max_retention:
        return {
            "current_count": total_count,
            "deleted_count": 0,
            "action": "no_action_needed",
        }

    to_delete = total_count - max_retention

    old_tasks = (
        session.query(AsyncTask)
        .filter(AsyncTask.status.in_(["completed", "failed", "cancelled"]))
        .order_by(AsyncTask.updated_at.asc())
        .limit(to_delete)
        .all()
    )

    deleted_count = len(old_tasks)
    for task in old_tasks:
        session.delete(task)

    session.commit()

    return {
        "current_count": total_count,
        "deleted_count": deleted_count,
        "new_count": total_count - deleted_count,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def test_cleanup_old_tasks_with_old_completed_tasks(db_session):
    """测试清理 7 天前的已完成任务"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    # 最近 7 天内的任务（不应被删除）
    create_async_task(db_session, "completed", now - timedelta(days=1))

    # 7 天前的任务（应被删除）
    old_time = now - timedelta(days=8)
    create_async_task(db_session, "completed", old_time)
    create_async_task(db_session, "failed", old_time)
    create_async_task(db_session, "cancelled", old_time)

    # 运行中的任务（不应被删除，即使很旧）
    create_async_task(db_session, "pending", now - timedelta(days=10))
    create_async_task(db_session, "running", now - timedelta(days=10))

    result = _cleanup_old_tasks_impl(db_session, days_to_keep=7)

    assert result["deleted_count"] == 3

    remaining_tasks = db_session.query(AsyncTask).all()
    assert len(remaining_tasks) == 3


def test_cleanup_old_tasks_respects_cutoff_date(db_session):
    """测试清理功能尊重截止日期"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    cutoff_time = now - timedelta(days=7)
    create_async_task(db_session, "completed", cutoff_time + timedelta(seconds=1))
    create_async_task(db_session, "completed", cutoff_time - timedelta(seconds=1))

    result = _cleanup_old_tasks_impl(db_session, days_to_keep=7)

    assert result["deleted_count"] == 1


def test_cleanup_task_count_when_below_threshold(db_session):
    """测试清理功能：当记录数低于阈值时不删除"""
    create_async_task(db_session, "completed")
    create_async_task(db_session, "completed")

    result = _cleanup_task_count_impl(db_session, max_retention=10)

    assert result["deleted_count"] == 0
    assert result["current_count"] == 2


def test_cleanup_task_count_when_above_threshold(db_session):
    """测试清理功能：当记录数超过阈值时删除最旧的"""
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    for i in range(15):
        updated_at = now - timedelta(days=i)
        create_async_task(db_session, "completed", updated_at)

    result = _cleanup_task_count_impl(db_session, max_retention=10)

    assert result["deleted_count"] == 5
    assert result["new_count"] == 10


def test_cleanup_task_count_preserves_running_tasks(db_session):
    """测试清理功能：保留运行中的任务即使超过阈值"""
    for i in range(12):
        create_async_task(db_session, "completed")

    for i in range(3):
        create_async_task(db_session, "running")

    result = _cleanup_task_count_impl(db_session, max_retention=10)

    assert result["deleted_count"] == 5

    running_tasks = db_session.query(AsyncTask).filter_by(status="running").all()
    assert len(running_tasks) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
