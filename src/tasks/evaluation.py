"""Celery 评估任务实现

run_evaluation_task 是异步评估执行的核心任务，负责：
- 加载 Evaluation 记录和配置
- 创建 TaskService 任务单元
- 集成 TaskService 执行引擎
- 定义进度回调和暂停检查
- 处理任务生命周期
- 与 TaskManager 同步状态
"""

from __future__ import annotations

import uuid
from typing import Any

from celery import Task
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask, Evaluation
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.task_service import TaskService, TaskUnit


def get_db_session() -> Session:
    """获取数据库会话（用于依赖注入和测试）"""
    engine = make_engine(business_database_url())
    session_factory = make_session_factory(engine)
    return session_factory()


class EvaluationTask(Task):
    """评估任务基类，处理数据库连接缓存"""

    _db_session: Session | None = None

    def after_return(self, *args, **kwargs):
        """任务完成后清理数据库连接"""
        if self._db_session is not None:
            self._db_session.close()
            self._db_session = None


@celery_app.task(
    bind=True,
    base=EvaluationTask,
    name="src.tasks.evaluation.run_evaluation_task",
    autoretry_for=(RedisConnectionError, ConnectionError),
    retry_kwargs={"max_retries": 3, "countdown": 10},
    retry_backoff=True,
    retry_backoff_max=300,
    acks_late=True,
    reject_on_worker_lost=True,
)
def run_evaluation_task(self, evaluation_id: str) -> dict[str, Any]:
    """执行评估任务

    Args:
        evaluation_id: 评估 ID

    Returns:
        任务结果字典，包含 evaluation_id, status, completed_units, total_units

    Raises:
        ValueError: 配置错误或业务错误
        FileNotFoundError: 必需资源不存在
    """
    db = get_db_session()
    task_manager = TaskManager(db)

    # 初始化变量，避免在异常处理中访问未定义的变量
    async_task = None
    evaluation = None

    try:
        # 1. 加载 Evaluation 和 AsyncTask 记录
        evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).first()
        if evaluation is None:
            raise ValueError(f"Evaluation {evaluation_id} not found")

        if not evaluation.async_task_id:
            raise ValueError(f"Evaluation {evaluation_id} has no associated async task")

        async_task = db.query(AsyncTask).filter(AsyncTask.id == evaluation.async_task_id).first()
        if async_task is None:
            raise ValueError(f"AsyncTask {evaluation.async_task_id} not found")

        # 2. 验证配置
        if not evaluation.strategy_names:
            raise ValueError("strategy_names cannot be empty")
        if not evaluation.problem_ids:
            raise ValueError("problem_ids cannot be empty")

        # 3. 更新状态为 running
        task_manager.update_task_status(async_task.id, "running")
        evaluation.status = "running"
        db.commit()

        # 4. 创建 TaskService 任务单元
        units = _create_task_units(evaluation.strategy_names, evaluation.problem_ids)
        config_fingerprint = TaskService.config_fingerprint({"evaluation_id": evaluation_id})
        dataset_fingerprint = TaskService._hash_json(evaluation.problem_ids)

        # 5. 创建或加载 TaskService 任务
        task_service = TaskService(root=f"data/tasks/{evaluation_id}")
        run_id = f"eval-{evaluation_id}"

        # 检查是否是恢复任务
        resume = False
        try:
            existing_record = task_service.get(run_id)
            if existing_record.state in ("paused", "failed"):
                resume = True
        except FileNotFoundError:
            pass

        if not resume:
            task_service.create(
                units=units,
                config_fingerprint=config_fingerprint,
                dataset_fingerprint=dataset_fingerprint,
                run_id=run_id,
            )

        # 6. 定义回调和检查函数
        def on_unit_finished(record, unit):
            """单元完成回调，更新进度"""
            evaluation.completed_count = record.completed_units
            db.commit()

            # 更新 Celery 进度
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": record.completed_units,
                    "total": record.total_units,
                    "message": f"Completed {record.completed_units}/{record.total_units} units"
                }
            )

        def should_pause(record):
            """检查是否应该暂停"""
            # 检查用户请求暂停
            current_async_task = db.query(AsyncTask).filter(AsyncTask.id == async_task.id).first()
            if current_async_task and current_async_task.status == "paused":
                return True

            # 检查预算上限
            if evaluation.budget_cap_usd is not None and evaluation.spent_usd >= evaluation.budget_cap_usd:
                return True

            return False

        def worker(unit: TaskUnit) -> dict:
            """占位 worker 函数，返回模拟结果"""
            return {
                "unit_id": unit.unit_id,
                "strategy": unit.strategy,
                "problem_id": unit.problem_id,
                "success": True,
                "mock": True
            }

        # 7. 执行 TaskService.run()
        final_record = task_service.run(
            run_id=run_id,
            worker=worker,
            max_workers=1,
            config_fingerprint=config_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            resume=resume,
            pause_when=should_pause,
            on_unit_finished=on_unit_finished,
        )

        # 8. 更新最终状态
        if final_record.state == "completed":
            task_manager.update_task_status(async_task.id, "completed")
            evaluation.status = "completed"
        elif final_record.state == "paused":
            task_manager.update_task_status(async_task.id, "paused")
            evaluation.status = "paused"
        elif final_record.state == "failed":
            task_manager.update_task_status(async_task.id, "failed", error_message=final_record.error)
            evaluation.status = "failed"
            evaluation.error_message = final_record.error
        elif final_record.state == "cancelled":
            task_manager.update_task_status(async_task.id, "cancelled")
            evaluation.status = "cancelled"

        db.commit()

        # 9. 返回结果
        return {
            "evaluation_id": evaluation_id,
            "status": final_record.state,
            "completed_units": final_record.completed_units,
            "total_units": final_record.total_units,
        }

    except (ValueError, FileNotFoundError) as e:
        # 业务错误：不重试
        if async_task is not None:
            task_manager.update_task_status(async_task.id, "failed", error_message=str(e))
        if evaluation is not None:
            evaluation.status = "failed"
            evaluation.error_message = str(e)
        db.commit()
        raise

    except Exception as e:
        # 其他错误：记录并传播（可能触发重试）
        if async_task is not None:
            task_manager.update_task_status(async_task.id, "failed", error_message=str(e))
        if evaluation is not None:
            evaluation.status = "failed"
            evaluation.error_message = str(e)
        db.commit()
        raise

    finally:
        db.close()


def _create_task_units(strategy_names: list[str], problem_ids: list[str]) -> list[TaskUnit]:
    """创建笛卡尔积的 TaskUnit 列表

    Args:
        strategy_names: 策略名称列表
        problem_ids: 问题 ID 列表

    Returns:
        TaskUnit 列表
    """
    units = []
    for strategy in strategy_names:
        for problem_id in problem_ids:
            unit = TaskUnit(
                unit_id=str(uuid.uuid4()),
                strategy=strategy,
                problem_id=problem_id,
                repeat_index=0,
            )
            units.append(unit)
    return units
