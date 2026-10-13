"""TaskManager 抽象层

统一管理异步任务的生命周期，作为服务层与 Celery 的桥梁。
"""

import uuid
from collections.abc import Callable
from datetime import datetime

from sqlalchemy.orm import Session

from api.db.models import AsyncTask
from src.celery_app import celery_app


class TaskManager:
    """异步任务管理器，提供任务创建、查询、更新、暂停和取消功能。"""

    def __init__(self, db_session: Session):
        """初始化 TaskManager。

        Args:
            db_session: SQLAlchemy 数据库会话
        """
        self.db = db_session

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

        try:
            celery_app.send_task(
                celery_task_name,
                args=celery_task_args,
                kwargs=celery_task_kwargs,
                task_id=celery_task_id,
            )
        except Exception:
            # 发布失败：把已落库的任务标记为 failed，避免留下永远 pending 的孤儿
            task.status = "failed"
            task.error_message = "failed to publish task to broker"
            if task.completed_at is None:
                task.completed_at = datetime.utcnow()
            self.db.commit()
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

        task.progress = progress
        task.status = status
        self.db.commit()

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

        task.status = status
        if error_message is not None:
            task.error_message = error_message

        # 更新时间戳
        if status in ("completed", "failed", "cancelled"):
            if task.completed_at is None:
                task.completed_at = datetime.utcnow()
        elif status == "running":
            if task.started_at is None:
                task.started_at = datetime.utcnow()

        self.db.commit()

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

        if task.status != "running":
            raise ValueError("Can only pause running tasks")

        task.status = "paused"
        self.db.commit()

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

        if task.status in ("completed", "failed"):
            raise ValueError("Cannot cancel completed or failed tasks")

        # 调用 Celery revoke 终止任务
        if task.celery_task_id:
            celery_app.control.revoke(task.celery_task_id, terminate=True)

        task.status = "cancelled"
        if task.completed_at is None:
            task.completed_at = datetime.utcnow()
        self.db.commit()

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
