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
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from celery import Task
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask, Evaluation, EvaluationResult
from src.celery_app import celery_app
from src.task_manager import TaskManager
from src.task_service import TaskService, TaskUnit

if TYPE_CHECKING:
    from sqlalchemy.orm import sessionmaker

    from api.db.models import Problem
    from src.models import LLMConfig


def get_db_session() -> Session:
    """获取数据库会话（用于依赖注入和测试）"""
    engine = make_engine(business_database_url())
    session_factory = make_session_factory(engine)
    return session_factory()


class EvaluationTask(Task):  # type: ignore[misc]
    """评估任务基类，处理数据库连接缓存"""

    _db_session: Session | None = None

    def after_return(self, *args: Any, **kwargs: Any) -> None:
        """任务完成后清理数据库连接"""
        if self._db_session is not None:
            self._db_session.close()
            self._db_session = None


@celery_app.task(  # type: ignore[untyped-decorator]
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
def run_evaluation_task(self: EvaluationTask, evaluation_id: str) -> dict[str, Any]:
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
        def on_unit_finished(record: Any, unit: TaskUnit) -> None:
            """单元完成回调，更新进度"""
            evaluation.completed_count = record.completed_units
            db.commit()

            # 更新 Celery 进度
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": record.completed_units,
                    "total": record.total_units,
                    "message": f"Completed {record.completed_units}/{record.total_units} units",
                },
            )

        def should_pause(record: Any) -> bool:
            """检查是否应该暂停"""
            # 检查用户请求暂停
            current_async_task = db.query(AsyncTask).filter(AsyncTask.id == async_task.id).first()
            if current_async_task and current_async_task.status == "paused":
                return True

            # 检查预算上限
            if (
                evaluation.budget_cap_usd is not None
                and evaluation.spent_usd >= evaluation.budget_cap_usd
            ):
                return True

            return False

        def worker(unit: TaskUnit) -> dict[str, Any]:
            """占位 worker 函数，返回模拟结果"""
            return {
                "unit_id": unit.unit_id,
                "strategy": unit.strategy,
                "problem_id": unit.problem_id,
                "success": True,
                "mock": True,
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
            task_manager.update_task_status(
                async_task.id, "failed", error_message=final_record.error
            )
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


@dataclass
class _EvalContext:
    """执行任何单元前解析出的运行时上下文。

    Attributes:
        llm_config: 已解析的模型凭证配置。
        problem_map: 命中题库的题目，按 problem_id 索引。
        missing_problems: 题库中缺失的 problem_id 集合（不 fail-fast）。
    """

    llm_config: LLMConfig
    problem_map: dict[str, Problem]
    missing_problems: set[str]


def _resolve_execution_context(
    evaluation: Evaluation, session_factory: sessionmaker[Session]
) -> _EvalContext:
    """在执行任何单元前 fail-fast 解析「model + 凭证 + 题目」。

    解析顺序：先 model，后凭证，最后题目（Design Doc §5.4 / §5.5）。

    - model 缺失 → 抛 ``ValueError``（含 "no model"）。
    - api_key_id 缺失或凭证不可解析 → 抛 ``ValueError``（含 "Credential
      unavailable"）；``AuthService.llm_config`` 抛出的 ``HTTPException`` 被转换并
      抑制上下文，绝不让 ``HTTPException`` 逃逸进 Celery。
    - 题目缺失 → 只记入 ``missing_problems``，不 fail-fast。

    调用方在既有 ``except (ValueError, FileNotFoundError)`` 分支置 ``failed``。
    """
    model = evaluation.model
    if not model:
        raise ValueError(f"Evaluation {evaluation.id} has no model configured")

    from fastapi import HTTPException

    from api.auth.config import AuthSettings
    from api.auth.service import AuthService
    from api.db.problem_store import ProblemStore

    api_key_id = evaluation.api_key_id
    if not api_key_id:
        raise ValueError(f"Credential unavailable: evaluation {evaluation.id} has no api_key_id")

    auth = AuthService(AuthSettings())
    try:
        llm_config = auth.llm_config(api_key_id, evaluation.user_id, model)
    except HTTPException as exc:
        raise ValueError(f"Credential unavailable: {exc.detail}") from None

    store = ProblemStore(session_factory)
    problem_map: dict[str, Problem] = {}
    missing: set[str] = set()
    for pid in evaluation.problem_ids:
        problem = store.get_by_problem_id(pid)
        if problem is not None:
            problem_map[pid] = problem
        else:
            missing.add(pid)
    return _EvalContext(llm_config=llm_config, problem_map=problem_map, missing_problems=missing)


def _record_unit_result(db: Session, evaluation: Evaluation, unit: TaskUnit) -> float:
    """把一个已完成/失败的 TaskUnit 映射为 EvaluationResult 行（Design Doc §5.8/§5.12）。

    以 ``(evaluation_id, problem_id, strategy_name)`` 为幂等键 upsert，返回本单元
    cost（供 Task 5/6 累计 ``spent_usd``）。**不**设置 ``completed_count`` /
    ``failed_count``：计数聚合归 Task 6 的 ``on_unit_finished``（Design Doc §5.11）。
    **不** ``commit``：提交时机属编排层（主线程），本 helper 只做 add/字段更新。

    Args:
        db: 业务数据库会话。
        evaluation: 当前 Evaluation ORM 对象。
        unit: 终态 TaskUnit（status 为 "completed" 或 "failed"）。

    Returns:
        本单元的 cost（美元）。completed 单元取 ``metadata.cost_usd``，否则 0.0。
    """
    if unit.status == "completed" and unit.result:
        data = unit.result
        meta = data.get("metadata") or {}
        status = data.get("status", "failed")
        metrics = {
            "success": status == "success",
            "failure_category": data.get("failure_category"),
            "failure_mode": data.get("failure_mode"),
            "difficulty": data.get("difficulty"),
            "total_tokens": data.get("total_tokens", 0),
            "execution_time_seconds": data.get("execution_time_seconds", 0.0),
            "cost_usd": meta.get("cost_usd", 0.0),
            "cost_unknown": meta.get("cost_unknown", False),
            "formal_evaluable": data.get("formal_evaluable", False),
            "quality_metrics": data.get("quality_metrics"),
        }
        error_message = data.get("error_message")
        cost = float(meta.get("cost_usd", 0.0))
    else:
        status, metrics, error_message, cost = "failed", None, unit.error, 0.0

    row = (
        db.query(EvaluationResult)
        .filter_by(
            evaluation_id=evaluation.id,
            problem_id=unit.problem_id,
            strategy_name=unit.strategy,
        )
        .first()
    )
    if row is None:
        row = EvaluationResult(
            id=str(uuid.uuid4()),
            evaluation_id=evaluation.id,
            problem_id=unit.problem_id,
            strategy_name=unit.strategy,
        )
        db.add(row)
    row.status = status
    row.metrics = metrics
    row.error_message = error_message
    return cost
