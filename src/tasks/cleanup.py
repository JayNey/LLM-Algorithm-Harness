"""Celery 后台清理任务实现

cleanup_old_tasks 定期清理已完成的异步任务记录。
由 Celery Beat 按日程触发，无需手动调用。
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from celery import Task
from sqlalchemy import and_
from sqlalchemy.orm import Session

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask
from src.celery_app import celery_app


def get_db_session() -> Session:
    """获取数据库会话"""
    engine = make_engine(business_database_url())
    session_factory = make_session_factory(engine)
    return session_factory()


class CleanupTask(Task):  # type: ignore[misc]
    """清理任务基类，处理数据库连接缓存"""

    _db_session: Session | None = None

    def after_return(self, *args: Any, **kwargs: Any) -> None:
        """任务完成后清理数据库连接"""
        if self._db_session is not None:
            self._db_session.close()
            self._db_session = None


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=CleanupTask,
    name="src.tasks.cleanup.cleanup_old_tasks",
)
def cleanup_old_tasks(self: CleanupTask, days_to_keep: int = 7) -> dict[str, Any]:
    """清理已完成的异步任务

    删除 N 天前的已完成任务记录（已成功、已失败或已取消）。
    保留进行中的任务和最近 N 天的已完成任务。

    Args:
        days_to_keep: 保留最近 N 天的任务记录（默认 7 天）

    Returns:
        dict: 清理结果 {"deleted_count": int, "timestamp": str}
    """
    session = get_db_session()
    try:
        # 计算截止时间
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_to_keep)
        cutoff_time = cutoff_time.replace(tzinfo=None)  # SQLite 不支持 timezone-aware datetime

        # 查询要删除的任务：已完成且在截止时间之前
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

        # 删除任务
        for task in old_tasks:
            session.delete(task)

        session.commit()

        result = {
            "deleted_count": deleted_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cutoff_date": cutoff_time.isoformat(),
        }

        self.update_state(state="SUCCESS", meta=result)
        return result

    except Exception as e:
        session.rollback()
        self.update_state(
            state="FAILURE",
            meta={
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise
    finally:
        session.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    bind=True,
    base=CleanupTask,
    name="src.tasks.cleanup.cleanup_task_count",
)
def cleanup_task_count(self: CleanupTask, max_retention: int = 10000) -> dict[str, Any]:
    """基于总数的清理策略

    如果 async_tasks 表的记录总数超过 max_retention，
    删除最旧的已完成任务直到总数降到阈值。

    Args:
        max_retention: 表保留的最大记录数（默认 10000）

    Returns:
        dict: 清理结果 {"current_count": int, "deleted_count": int}
    """
    session = get_db_session()
    try:
        # 获取当前记录总数
        total_count = session.query(AsyncTask).count()

        if total_count <= max_retention:
            return {
                "current_count": total_count,
                "deleted_count": 0,
                "action": "no_action_needed",
            }

        # 需要删除的数量
        to_delete = total_count - max_retention

        # 获取要删除的最旧已完成任务
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

        result = {
            "current_count": total_count,
            "deleted_count": deleted_count,
            "new_count": total_count - deleted_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        self.update_state(state="SUCCESS", meta=result)
        return result

    except Exception as e:
        session.rollback()
        self.update_state(
            state="FAILURE",
            meta={
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )
        raise
    finally:
        session.close()
