"""Tests for the celery cleanup tasks over the business database (#149)."""

from datetime import timedelta
from unittest.mock import Mock, patch

from api.db import (
    AsyncTask,
    business_database_url,
    make_engine,
    make_session_factory,
    run_migrations,
)
from api.db.models import utcnow
from src.tasks.cleanup import CleanupTask, cleanup_old_tasks, cleanup_task_count


def _task(task_id, status, *, age_days=0, unique_suffix=""):
    old = utcnow() - timedelta(days=age_days)
    return AsyncTask(
        id=task_id,
        celery_task_id=f"celery-{task_id}{unique_suffix}",
        task_type="benchmark",
        entity_id=f"entity-{task_id}",
        user_id="user-1",
        status=status,
        created_at=old,
        updated_at=old,
    )


def _seed(**tasks):
    """Create the schema and insert the given tasks; return a session factory."""
    url = business_database_url()
    run_migrations(url)
    factory = make_session_factory(make_engine(url))
    with factory() as session, session.begin():
        for task in tasks.values():
            session.add(task)
    return factory


def _remaining_ids(factory):
    with factory() as session:
        return sorted(task.id for task in session.query(AsyncTask).all())


class TestCleanupOldTasks:
    def test_deletes_only_old_terminal_tasks(self):
        factory = _seed(
            old_completed=_task("old-completed", "completed", age_days=30),
            old_failed=_task("old-failed", "failed", age_days=30),
            old_cancelled=_task("old-cancelled", "cancelled", age_days=30),
            recent_completed=_task("recent-completed", "completed", age_days=1),
            running=_task("running", "running", age_days=30),
        )

        with patch.object(cleanup_old_tasks, "update_state"):
            result = cleanup_old_tasks.__wrapped__(days_to_keep=7)

        assert result["deleted_count"] == 3
        assert _remaining_ids(factory) == ["recent-completed", "running"]

    def test_keeps_everything_within_retention_window(self):
        factory = _seed(
            recent=_task("recent", "completed", age_days=2),
        )

        with patch.object(cleanup_old_tasks, "update_state"):
            result = cleanup_old_tasks.__wrapped__(days_to_keep=7)

        assert result["deleted_count"] == 0
        assert _remaining_ids(factory) == ["recent"]


class TestCleanupTaskCount:
    def test_no_action_below_retention(self):
        factory = _seed(
            one=_task("one", "completed", age_days=1),
            two=_task("two", "running", age_days=1),
        )

        with patch.object(cleanup_task_count, "update_state"):
            result = cleanup_task_count.__wrapped__(max_retention=100)

        assert result["deleted_count"] == 0
        assert result["action"] == "no_action_needed"
        assert _remaining_ids(factory) == ["one", "two"]

    def test_trims_oldest_terminal_tasks_first(self):
        factory = _seed(
            old_terminal_a=_task("old-terminal-a", "completed", age_days=40),
            old_terminal_b=_task("old-terminal-b", "failed", age_days=30),
            old_running=_task("old-running", "running", age_days=20),
            recent_terminal=_task("recent-terminal", "completed", age_days=1),
            recent_running=_task("recent-running", "running", age_days=0),
        )

        with patch.object(cleanup_task_count, "update_state"):
            result = cleanup_task_count.__wrapped__(max_retention=3)

        # total 5 > 3, so the 2 oldest terminal tasks are removed; the
        # running task is protected even though it is older.
        assert result["deleted_count"] == 2
        assert _remaining_ids(factory) == [
            "old-running",
            "recent-running",
            "recent-terminal",
        ]


class TestCleanupTaskBase:
    def test_after_return_closes_cached_session(self):
        task = CleanupTask()
        session = Mock()
        task._db_session = session

        task.after_return()

        session.close.assert_called_once()
        assert task._db_session is None

    def test_after_return_without_session_is_noop(self):
        task = CleanupTask()
        task.after_return()  # must not raise
