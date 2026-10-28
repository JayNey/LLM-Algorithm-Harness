"""TaskManager 抽象层

统一管理异步任务的生命周期，作为服务层与 Celery 的桥梁。
"""

import hashlib
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, false, func, select, text, update
from sqlalchemy.orm import Session

from api.config import settings
from api.db.models import ABTest, AsyncTask, Evaluation, Experiment, utcnow
from api.monitoring.execution_logs import record_execution_event
from src.celery_app import celery_app

_EVALUATION_CELERY_TASK = "src.tasks.evaluation.run_evaluation_task"


class EvaluationConcurrencyLimitExceeded(ValueError):
    """The user has reserved all evaluation admission slots."""


def _request_evaluation_cancel(evaluation_id: str) -> None:
    """请求评估检查点在下一个单元边界停止。

    检查点尚未创建时忽略缺失。worker 与这里使用同一相对目录和运行标识。
    """
    from src.task_service import TaskService

    service = TaskService(root=f"data/tasks/{evaluation_id}")
    try:
        service.request_cancel(f"eval-{evaluation_id}")
    except FileNotFoundError:
        return


class TaskManager:
    """异步任务管理器，提供任务创建、查询、更新、暂停和取消功能。"""

    def __init__(self, db_session: Session):
        """初始化 TaskManager。

        Args:
            db_session: SQLAlchemy 数据库会话
        """
        self.db = db_session

    def _lock_business_task(self, task: AsyncTask) -> None:
        """Serialize paired state writes on SQLite as well as PostgreSQL."""
        if task.task_type in ("ab_test", "experiment"):
            with self.db.no_autoflush:
                self.db.execute(
                    update(AsyncTask)
                    .where(AsyncTask.id == task.id)
                    .values(id=AsyncTask.id, updated_at=AsyncTask.updated_at)
                    .execution_options(synchronize_session=False)
                )
                self.db.refresh(task)

    def _sync_business(self, task: AsyncTask) -> None:
        """Mirror owned business state in the same transaction as its task."""
        row: ABTest | Experiment | None
        if task.task_type == "ab_test":
            row = self.db.get(ABTest, task.entity_id)
        elif task.task_type == "experiment":
            row = self.db.get(Experiment, task.entity_id, populate_existing=True)
        else:
            return
        if row is None or row.user_id != task.user_id:
            return
        row.status = task.status
        row.error_message = task.error_message
        row.started_at = task.started_at
        row.completed_at = task.completed_at
        row.updated_at = utcnow()

    def _experiment_transition_blocked(self, task: AsyncTask, status: str) -> bool:
        if task.task_type != "experiment":
            return False
        self._lock_business_task(task)
        return task.status in ("completed", "failed", "cancelled") or (
            task.status == "paused" and status != "cancelled"
        )

    def _check_evaluation_capacity(self, task_type: str, user_id: str) -> None:
        """Serialize admission in the shared DB until task commit or rollback.

        Pending messages reserve capacity before workers start them. No counter
        needs repairing: completion, pause and cancellation release capacity by
        changing the persisted task status. All submitters use the same limit.
        """
        if task_type != "evaluation":
            return
        with self.db.no_autoflush:
            dialect = self.db.get_bind().dialect.name
            if dialect == "sqlite":
                # A zero-row UPDATE acquires SQLite's writer lock without
                # changing any record, even when this is the first submission.
                self.db.execute(
                    update(AsyncTask)
                    .where(false())
                    .values(id=AsyncTask.id)
                    .execution_options(synchronize_session=False)
                )
            elif dialect == "postgresql":
                # Python hash() varies per process. Use a namespaced stable
                # signed bigint for PostgreSQL's transaction-scoped lock.
                key = int.from_bytes(
                    hashlib.blake2b(
                        ("evaluation-admission:" + user_id).encode(), digest_size=8
                    ).digest(),
                    "big",
                    signed=True,
                )
                self.db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})
            else:
                raise ValueError("Evaluation concurrency requires SQLite or PostgreSQL")
        self.db.flush()
        active = self.db.execute(
            select(func.count())
            .select_from(AsyncTask)
            .where(
                AsyncTask.user_id == user_id,
                AsyncTask.task_type == "evaluation",
                AsyncTask.status.in_(("pending", "running")),
            )
        ).scalar_one()
        if active >= settings.MAX_CONCURRENT_EVALUATIONS_PER_USER:
            raise EvaluationConcurrencyLimitExceeded("User evaluation concurrency limit reached")

    def create_task(
        self,
        task_type: str,
        entity_id: str,
        user_id: str,
        celery_task_name: str,
        celery_task_args: tuple = (),
        celery_task_kwargs: dict | None = None,
    ) -> AsyncTask:
        """创建异步任务并提交到 Celery。

        流程：
        1. 创建 AsyncTask 记录，状态为 pending
        2. flush 到数据库但不提交
        3. 提交任务到 Celery，获得 celery_task_id
        4. 更新 AsyncTask.celery_task_id 字段
        5. commit 提交到数据库

        Args:
            task_type: 任务类型，如 "evaluation", "experiment", "import", "benchmark"
            entity_id: 业务实体 ID，如 evaluation_id
            user_id: 用户 ID
            celery_task_name: Celery 任务名，如 "src.tasks.evaluation.run_evaluation_task"
            celery_task_args: Celery 任务位置参数
            celery_task_kwargs: Celery 任务关键字参数

        Returns:
            创建的 AsyncTask 实例
        """
        if celery_task_kwargs is None:
            celery_task_kwargs = {}

        self._check_evaluation_capacity(task_type, user_id)

        # 创建 AsyncTask 记录
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id="",  # 稍后更新
            task_type=task_type,
            entity_id=entity_id,
            user_id=user_id,
            status="pending",
        )

        # Flush 到数据库但不提交
        self.db.add(task)
        self.db.flush()

        # 提交任务到 Celery
        celery_result = celery_app.send_task(
            celery_task_name,
            args=celery_task_args,
            kwargs=celery_task_kwargs,
        )

        # 更新 celery_task_id
        task.celery_task_id = celery_result.id

        # 提交到数据库
        self.db.commit()

        return task

    def enqueue_task(
        self,
        task_type: str,
        entity_id: str,
        user_id: str,
        celery_task_name: str,
        celery_task_args: tuple = (),
        celery_task_kwargs: dict | None = None,
        on_before_publish: Callable[[AsyncTask], None] | None = None,
    ) -> AsyncTask:
        """创建异步任务：先落库，再发布到 Celery。

        与 create_task 的区别在于消除入队时序竞态：预生成 celery_task_id，在
        send_task 之前提交 AsyncTask 记录，并通过 on_before_publish 钩子让调用方
        在发布前建立业务关联（如 evaluation.async_task_id）。这样 worker 即使在
        发布后立即取到消息，也一定能读到已落库的任务记录与关联。

        Args:
            task_type: 任务类型，如 "evaluation"
            entity_id: 业务实体 ID，如 evaluation_id
            user_id: 用户 ID
            celery_task_name: Celery 任务名
            celery_task_args: Celery 任务位置参数
            celery_task_kwargs: Celery 任务关键字参数
            on_before_publish: 发布前回调，接收已 flush 的 AsyncTask，可用于
                在同一事务内建立业务实体到该任务的关联

        Returns:
            创建的 AsyncTask 实例

        Raises:
            原始发布异常：send_task 失败时把任务置为 failed 后原样抛出
        """
        if celery_task_kwargs is None:
            celery_task_kwargs = {}

        self._check_evaluation_capacity(task_type, user_id)

        # 预生成 celery_task_id，使记录可以在发布前落库
        celery_task_id = str(uuid.uuid4())
        task = AsyncTask(
            id=str(uuid.uuid4()),
            celery_task_id=celery_task_id,
            task_type=task_type,
            entity_id=entity_id,
            user_id=user_id,
            status="pending",
        )
        self.db.add(task)
        self.db.flush()

        # 发布前建立业务关联（与任务记录同一事务提交）
        if on_before_publish is not None:
            on_before_publish(task)

        # 先落库，确保 worker 取到消息时一定能解析到任务记录与关联
        self.db.commit()
        record_execution_event(task, "task.queued")

        try:
            celery_app.send_task(
                celery_task_name,
                args=celery_task_args,
                kwargs=celery_task_kwargs,
                task_id=celery_task_id,
            )
        except Exception:
            # A publish timeout does not prove the message was never delivered.
            # Do not overwrite a task already started, stopped or completed elsewhere.
            self.db.rollback()
            failed = self.db.execute(
                update(AsyncTask)
                .where(AsyncTask.id == task.id, AsyncTask.status == "pending")
                .values(
                    status="failed",
                    error_message="failed to publish task to broker",
                    completed_at=datetime.utcnow(),
                )
            )
            if cast(CursorResult[Any], failed).rowcount:
                self.db.refresh(task)
                self._sync_business(task)
                self.db.commit()
                record_execution_event(task, "task.failed")
            else:
                self.db.rollback()
            raise

        return task

    def get_task(self, task_id: str, user_id: str | None = None) -> AsyncTask:
        """获取任务，自动同步 Celery 状态。

        流程：
        1. 按 task_id 查询（如果提供 user_id，添加权限过滤）
        2. 如果任务不存在，抛出 ValueError
        3. 如果任务有 celery_task_id 且状态为 pending/running，调用 _sync_celery_state() 从 Celery 同步最新状态
        4. 返回任务记录

        Args:
            task_id: 任务 ID
            user_id: 用户 ID（可选），用于权限验证

        Returns:
            AsyncTask 实例

        Raises:
            ValueError: 任务不存在或访问被拒绝
        """
        query = self.db.query(AsyncTask).filter(AsyncTask.id == task_id)

        if user_id is not None:
            query = query.filter(AsyncTask.user_id == user_id)

        task = query.first()

        if task is None:
            if user_id is not None:
                raise ValueError("Task not found or access denied")
            else:
                raise ValueError("Task not found")

        # 同步 Celery 状态
        if task.celery_task_id and task.status in ("pending", "running"):
            self._sync_celery_state(task)

        return task

    def _sync_celery_state(self, task: AsyncTask) -> None:
        """从 Celery 读取任务状态并更新到数据库。

        Args:
            task: AsyncTask 实例
        """
        # 获取 Celery 任务状态
        celery_result = celery_app.AsyncResult(task.celery_task_id)
        celery_state = celery_result.state

        if task.task_type in ("ab_test", "experiment"):
            # Only the business worker may start these tasks. STARTED is
            # emitted by Celery before the worker body acquires that claim.
            if celery_state in ("FAILURE", "REVOKED"):
                self._lock_business_task(task)
                if task.status not in ("pending", "running"):
                    return
                status = "failed" if celery_state == "FAILURE" else "cancelled"
                message = str(celery_result.info) if celery_state == "FAILURE" else None
                self.update_task_status(task.id, status, error_message=message)
            return

        # 映射 Celery 状态到数据库状态
        if celery_state == "STARTED":
            task.status = "running"
            if task.started_at is None:
                task.started_at = datetime.utcnow()
            self.db.commit()

        elif celery_state == "PROGRESS":
            task.status = "running"
            # 更新进度信息
            if celery_result.info and isinstance(celery_result.info, dict):
                task.progress = celery_result.info
            self.db.commit()

        elif celery_state == "FAILURE":
            task.status = "failed"
            task.error_message = str(celery_result.info) if celery_result.info else "Task failed"
            if task.completed_at is None:
                task.completed_at = datetime.utcnow()
            self.db.commit()

    def update_task_progress(
        self,
        task_id: str,
        progress: dict,
        status: str,
    ) -> None:
        """更新任务进度。

        Args:
            task_id: 任务 ID
            progress: 进度数据字典
            status: 任务状态

        Raises:
            ValueError: 任务不存在
        """
        task = self.db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if task is None:
            raise ValueError("Task not found")

        if self._experiment_transition_blocked(task, status):
            self.db.commit()
            return
        task.progress = progress
        self._record_execution_times(task, status)
        task.status = status
        if task.task_type == "experiment":
            self._sync_business(task)
        self.db.commit()
        record_execution_event(task, "task.progress", progress)

    def update_task_status(
        self,
        task_id: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        """更新任务状态。

        Args:
            task_id: 任务 ID
            status: 任务状态
            error_message: 错误信息（可选）

        Raises:
            ValueError: 任务不存在
        """
        task = self.db.query(AsyncTask).filter(AsyncTask.id == task_id).first()
        if task is None:
            raise ValueError("Task not found")

        if self._experiment_transition_blocked(task, status):
            self.db.commit()
            return
        task.status = status
        if error_message is not None:
            task.error_message = error_message

        self._record_execution_times(task, status)
        self._sync_business(task)

        self.db.commit()
        event = {"running": "task.started", "pending": "task.queued"}.get(status, "task." + status)
        record_execution_event(task, event)

    @staticmethod
    def _record_execution_times(task: AsyncTask, status: str) -> None:
        """Keep first execution start and the end of the latest execution."""
        if status == "running":
            if task.started_at is None:
                task.started_at = datetime.utcnow()
            task.completed_at = None
        elif status in ("completed", "failed", "cancelled") and task.completed_at is None:
            task.completed_at = datetime.utcnow()

    def pause_task(self, task_id: str, user_id: str) -> AsyncTask:
        """暂停任务。

        仅允许暂停 running 状态的任务。不涉及 Celery revoke（由任务自行检查状态）。

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            更新后的 AsyncTask 实例

        Raises:
            ValueError: 任务不存在、访问被拒绝或状态不允许暂停
        """
        task = self.get_task(task_id, user_id)

        self._lock_business_task(task)
        if task.status != "running":
            raise ValueError("Can only pause running tasks")

        task.status = "paused"
        self._sync_business(task)
        self.db.commit()
        record_execution_event(task, "task.paused")

        return task

    def cancel_task(self, task_id: str, user_id: str) -> AsyncTask:
        """取消任务。

        允许取消 pending/running/paused 状态的任务，调用 celery_app.control.revoke() 终止 Celery 任务。

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            更新后的 AsyncTask 实例

        Raises:
            ValueError: 任务不存在、访问被拒绝或状态不允许取消
        """
        task = self.get_task(task_id, user_id)

        self._lock_business_task(task)
        if task.status in ("completed", "failed"):
            raise ValueError("Cannot cancel completed or failed tasks")

        if task.task_type == "experiment":
            experiment = self.db.get(
                Experiment, task.entity_id, populate_existing=True, with_for_update=True
            )
            if (
                experiment is not None
                and experiment.user_id == task.user_id
                and experiment.status in ("completed", "failed")
            ):
                raise ValueError("Cannot cancel completed or failed experiments")

        if task.task_type == "experiment" and task.status == "cancelled":
            self.db.commit()
            return task

        # 调用 Celery revoke 终止任务
        if task.celery_task_id:
            celery_app.control.revoke(task.celery_task_id, terminate=True)

        if task.task_type == "evaluation":
            _request_evaluation_cancel(task.entity_id)

        task.status = "cancelled"
        if task.completed_at is None:
            task.completed_at = datetime.utcnow()
        self._sync_business(task)
        self.db.commit()
        record_execution_event(task, "task.cancelled")

        return task

    def resume_task(self, task_id: str, user_id: str) -> AsyncTask:
        """重新入队一个已暂停的评估任务。

        沿用同一条 AsyncTask。先把任务和关联评估写成 pending 并提交，再发布
        Celery 消息。非暂停、非评估或不属于调用方的任务会被拒绝，且不改记录。

        Args:
            task_id: 任务 ID
            user_id: 用户 ID

        Returns:
            更新后的同一条 AsyncTask

        Raises:
            ValueError: 任务不存在、访问被拒绝、状态不允许恢复，或评估未关联该任务
        """
        task = self.get_task(task_id, user_id)
        if task.status != "paused":
            raise ValueError("Can only resume paused tasks")
        if task.task_type != "evaluation":
            raise ValueError("Can only resume evaluation tasks")

        evaluation = (
            self.db.query(Evaluation)
            .filter(Evaluation.id == task.entity_id, Evaluation.user_id == user_id)
            .first()
        )
        if evaluation is None or evaluation.async_task_id != task.id:
            raise ValueError("Evaluation is not linked to this task")

        self._check_evaluation_capacity(task.task_type, user_id)
        # A competing resume may have committed while admission waited. Reload
        # under the same user lock before reserving this existing task again.
        self.db.refresh(task)
        self.db.refresh(evaluation)
        if task.status != "paused" or task.user_id != user_id:
            raise ValueError("Can only resume paused tasks owned by the user")
        if evaluation.async_task_id != task.id or evaluation.user_id != user_id:
            raise ValueError("Evaluation is not linked to this task")

        celery_task_id = str(uuid.uuid4())
        task.celery_task_id = celery_task_id
        task.status = "pending"
        evaluation.status = "pending"
        evaluation.updated_at = utcnow()
        self.db.commit()
        record_execution_event(task, "task.resumed")

        try:
            celery_app.send_task(
                _EVALUATION_CELERY_TASK,
                args=(task.entity_id,),
                task_id=celery_task_id,
            )
        except Exception:
            task.status = "failed"
            task.error_message = "failed to publish task to broker"
            if task.completed_at is None:
                task.completed_at = datetime.utcnow()
            self.db.commit()
            record_execution_event(task, "task.failed")
            raise

        return task

    def list_tasks(
        self,
        user_id: str,
        task_type: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AsyncTask], int]:
        """列出用户任务。

        Args:
            user_id: 用户 ID
            task_type: 任务类型过滤（可选）
            status: 任务状态过滤（可选）
            limit: 返回数量限制
            offset: 分页偏移量

        Returns:
            (任务列表, 总数) 元组
        """
        query = self.db.query(AsyncTask).filter(AsyncTask.user_id == user_id)

        if task_type is not None:
            query = query.filter(AsyncTask.task_type == task_type)

        if status is not None:
            query = query.filter(AsyncTask.status == status)

        # 获取总数
        total = query.count()

        # 分页查询
        tasks = query.order_by(AsyncTask.created_at.desc()).limit(limit).offset(offset).all()

        return tasks, total
