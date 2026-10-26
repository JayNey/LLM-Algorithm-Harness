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
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from celery import Task
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError
from sqlalchemy.orm import Session, sessionmaker

from api.db.engine import business_database_url, make_engine, make_session_factory
from api.db.models import AsyncTask, Evaluation, EvaluationResult, utcnow
from api.monitoring.execution_logs import record_execution_event
from api.progress import publish_progress
from api.services.cost_service import CostService
from src.celery_app import celery_app
from src.harness import AlgorithmHarness
from src.models import (
    ExecutionResult,
    HarnessConfig,
    SandboxConfig,
    StrategyConfig,
)
from src.models import Problem as DomainProblem
from src.task_manager import TaskManager
from src.task_service import TaskService, TaskUnit
from src.tasks.support import task_progress

if TYPE_CHECKING:
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

        if async_task.status == "cancelled":
            evaluation.status = "cancelled"
            db.commit()
            return {
                "evaluation_id": evaluation_id,
                "status": "cancelled",
                "completed_units": 0,
                "total_units": 0,
            }

        # 2. 验证配置
        if not evaluation.strategy_names:
            raise ValueError("strategy_names cannot be empty")
        if not evaluation.problem_ids:
            raise ValueError("problem_ids cannot be empty")

        # 2b. 执行任何单元前 fail-fast 解析 model + 凭证 + 题目（Design Doc §5.4/§5.5）。
        # 必须复用 db 同一 engine：sessionmaker(bind=db.get_bind()) 保证 ProblemStore 与
        # evaluation 读写同一 DB（测试中 db 为内存 session，新建 engine 会破坏隔离且查不到
        # 题目）。解析抛 ValueError（缺 model / 凭证不可解析）→ 落入既有 except 置 failed，
        # 不发起任何单元、无 EvaluationResult 行。
        session_factory = sessionmaker(bind=db.get_bind())
        ctx = _resolve_execution_context(evaluation, session_factory)

        # 3. 更新状态为 running
        task_manager.update_task_status(async_task.id, "running")
        evaluation.status = "running"
        db.commit()
        publish_progress(
            evaluation_id,
            "task.started",
            {
                "status": "running",
                "total_units": len(evaluation.problem_ids) * len(evaluation.strategy_names),
            },
        )

        # 3b. 构造 harness 并为每策略预建一次 runtime（Design Doc §5.6）。
        # _build_harness 抛 RuntimeError（sandbox preflight 失败）/ValueError（未知策略）
        # → 落入既有 except 置 failed（RuntimeError 走通用 except Exception，不在
        # autoretry_for=(RedisConnectionError, ConnectionError) 内，不会无限重试）。
        harness, strategy_configs, runtimes = _build_harness(ctx, evaluation.strategy_names)

        # 4. 创建 TaskService 任务单元
        units = _create_task_units(evaluation.strategy_names, evaluation.problem_ids)
        config_fingerprint = TaskService.config_fingerprint({"evaluation_id": evaluation_id})
        dataset_fingerprint = TaskService._hash_json(evaluation.problem_ids)

        # 5. 创建或加载 TaskService 任务
        task_service = TaskService(root=f"data/tasks/{evaluation_id}")
        run_id = f"eval-{evaluation_id}"

        # worker 丢失后重投递会留下 running 检查点，同样需要恢复中断单元。
        resume = False
        try:
            existing_record = task_service.get(run_id)
            if existing_record.state in ("running", "paused", "failed"):
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
        execution_strategies: dict[str, str] = {}

        def report_progress(record: Any, unit: TaskUnit, finished: int) -> None:
            """把即将执行或刚结束单元的进度写入任务记录和 Celery。

            只在任务仍为 running 时写入，避免把已暂停的任务通过 PROGRESS 状态盖回去。
            """
            progress = task_progress(
                finished,
                record.total_units,
                f"{unit.strategy}/{unit.problem_id}",
            )
            current_async_task = (
                db.query(AsyncTask)
                .populate_existing()
                .filter(AsyncTask.id == async_task.id)
                .first()
            )
            if current_async_task is None or current_async_task.status != "running":
                return
            current_async_task.progress = progress
            db.commit()
            record_execution_event(current_async_task, "task.progress", progress)
            self.update_state(state="PROGRESS", meta=progress)

        def on_unit_started(record: Any, unit: TaskUnit) -> None:
            """单元提交前上报：百分比是已完成比例，当前步骤是即将执行的单元。"""
            selected = execution_strategies.get(unit.unit_id, unit.strategy)
            if selected not in runtimes:
                strategy_configs[selected] = StrategyConfig(name=selected)
                runtimes[selected] = harness._prepare_strategy_runtime(strategy_configs[selected])
            finished = sum(1 for item in record.units if item.status in {"completed", "failed"})
            report_progress(record, unit, finished)
            record_execution_event(
                async_task,
                "unit.started",
                {"problem_id": unit.problem_id, "strategy": unit.strategy},
            )

        def on_unit_finished(record: Any, unit: TaskUnit) -> None:
            """单元完成回调（主线程，可触碰 db）：落库 + 累计成本 + 重算计数 + 报进度。

            计数按 record.units 全量重算（不用 record.completed_units，它含 failed），
            满足 completed_count + failed_count == 已完成单元数（Design Doc §5.11）。
            _record_unit_result 自身不 commit，由此处统一 commit。
            """
            cost = _record_unit_result(db, evaluation, unit)
            evaluation.spent_usd = float(
                Decimal(str(evaluation.spent_usd or 0)) + Decimal(str(cost))
            )
            evaluation.completed_count = sum(1 for u in record.units if u.status == "completed")
            evaluation.failed_count = sum(1 for u in record.units if u.status == "failed")
            db.commit()
            report_progress(record, unit, record.completed_units)
            record_execution_event(
                async_task,
                "unit.failed" if unit.status == "failed" else "unit.completed",
                {"problem_id": unit.problem_id, "strategy": unit.strategy, "status": unit.status},
            )

            # WebSocket 实时进度（best-effort：Redis 故障只丢事件不伤任务）
            total_units = record.total_units or 1
            publish_progress(
                evaluation.id,
                "problem.completed",
                {
                    "problem_id": unit.problem_id,
                    "strategy": unit.strategy,
                    "status": unit.status,
                    "cost_usd": cost,
                },
            )
            publish_progress(
                evaluation.id,
                "task.progress",
                {
                    "completed": evaluation.completed_count,
                    "failed": evaluation.failed_count,
                    "total": total_units,
                    "percentage": round(evaluation.completed_count / total_units * 100, 2),
                    "current_problem": unit.problem_id,
                    "current_strategy": unit.strategy,
                },
            )

        def should_pause(record: Any) -> bool:
            """检查是否应该暂停。

            用户暂停分支必须跨进程可见：API 进程（另一 DB 连接）通过 pause_task()
            把 AsyncTask 写成 "paused"，而本 worker session 的业务 engine 配
            expire_on_commit=False——该对象已在 identity map 中，普通 ``.first()``
            命中缓存实例、不重新 SELECT，会永远看不到外部写入。故用
            ``populate_existing()`` 强制从 DB 重读并刷新该 AsyncTask 实例属性，绕过
            identity map 短路。**只**作用于被查询的 AsyncTask，不 refresh evaluation
            等其他对象，以免丢弃主线程待提交状态。
            """
            # 检查用户请求暂停（强制重读，跨进程可见）
            current_async_task = (
                db.query(AsyncTask)
                .populate_existing()
                .filter(AsyncTask.id == async_task.id)
                .first()
            )
            if current_async_task and current_async_task.status == "paused":
                return True

            # 检查预算上限
            if (
                evaluation.budget_cap_usd is not None
                and evaluation.spent_usd >= evaluation.budget_cap_usd
            ):
                return True

            budget = CostService.execution_budget(db, evaluation.user_id)
            queued = next((unit for unit in record.units if unit.status == "queued"), None)
            if budget is None or queued is None:
                if queued is not None:
                    execution_strategies.pop(queued.unit_id, None)
                return False
            problem = ctx.problem_map.get(queued.problem_id)
            reached = budget["global_reached"] or (
                problem is not None and problem.difficulty in budget["exhausted_difficulties"]
            )
            if reached and budget["action"] == "pause":
                return True
            execution_strategies[queued.unit_id] = (
                "vanilla" if reached and budget["action"] == "downgrade" else queued.strategy
            )
            return False

        # 真实 worker（Design Doc §5.7）：闭包捕获 harness/策略配置/预建 runtime/只读题目
        # 映射，绝不引用 db（worker 跑在 executor 线程，跨线程触碰 session 会损坏连接）。
        # worker 返回 ExecutionResult，由 TaskService._serialize_result 序列化入 unit.result。
        worker = _make_worker(
            harness,
            strategy_configs,
            runtimes,
            ctx.problem_map,
            ctx.missing_reasons,
            execution_strategies=execution_strategies,
        )

        # 7. 执行 TaskService.run()
        final_record = task_service.run(
            run_id=run_id,
            worker=worker,
            max_workers=1,
            config_fingerprint=config_fingerprint,
            dataset_fingerprint=dataset_fingerprint,
            resume=resume,
            pause_when=should_pause,
            on_unit_started=on_unit_started,
            on_unit_finished=on_unit_finished,
        )

        # 8. 更新最终状态。调用方可能已在另一个连接把任务写成 cancelled；
        # 这里必须重新读取，避免用检查点的完成状态把它盖回去。
        current_async_task = (
            db.query(AsyncTask).populate_existing().filter(AsyncTask.id == async_task.id).first()
        )
        if current_async_task is not None and current_async_task.status == "cancelled":
            evaluation.status = "cancelled"
            db.commit()
            return {
                "evaluation_id": evaluation_id,
                "status": "cancelled",
                "completed_units": final_record.completed_units,
                "total_units": final_record.total_units,
            }

        if final_record.state == "completed":
            task_manager.update_task_status(async_task.id, "completed")
            evaluation.status = "completed"
            if evaluation.completed_at is None:
                evaluation.completed_at = utcnow()
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

        # 终态事件推送（best-effort）
        terminal_event = {
            "completed": "task.completed",
            "paused": "task.paused",
            "failed": "task.failed",
            "cancelled": "task.cancelled",
        }.get(final_record.state)
        if terminal_event:
            publish_progress(
                evaluation_id,
                terminal_event,
                {
                    "status": final_record.state,
                    "completed": evaluation.completed_count,
                    "failed": evaluation.failed_count,
                    "total_units": final_record.total_units,
                    "error_message": evaluation.error_message,
                },
            )

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
        missing_problems: 题库中不可用（缺失或非法）的 problem_id 集合（不 fail-fast）。
        missing_reasons: ``problem_id -> 不可用原因文本``。区分「查不到」
            （``"not found in problem store"``）与「行存在但数据非法」
            （``"invalid/incomplete problem data: ..."``），供 worker 把真实原因
            随单元失败信息下传，避免非法数据被伪装成「not found」误导用户重复导入。
    """

    llm_config: LLMConfig
    problem_map: dict[str, DomainProblem]
    missing_problems: set[str]
    missing_reasons: dict[str, str] = field(default_factory=dict)


def _to_domain_problem(row: Problem) -> DomainProblem:
    """把 ORM ``api.db.models.Problem`` 行转换成 domain ``src.models.Problem``。

    ``ProblemStore.get_by_problem_id`` 返回 ORM 行，但 harness ``_execute_problem``
    消费 domain Problem（需 ``model_copy``/``hidden_test_cases``/``unsupported_reason``
    等 pydantic 成员）。ORM 列与 dataset 字段 1:1；domain 的
    ``migrate_legacy_test_cases``(mode="before") validator 会把 ``test_cases`` 键归为
    ``public_test_cases``（``hidden_test_cases`` 为空、
    ``migration_status="legacy_test_cases_as_public"``）。所有字段均为 eagerly-loaded
    列，``get_by_problem_id`` 的 session 关闭后读取仍安全（无 lazy 关系）。

    值为 ``None`` 的 ORM 列**不传**给 domain：真实题库（``data/problems.json``）不含
    ``source_platform``/``source_url`` 键，导入后列为 NULL，而 domain 的
    ``source_platform: str = Field("legacy")`` 是非 Optional——显式传 ``None`` 会触发
    ``ValidationError``，令全部真实题目被判为 missing。省略这些键让 domain 默认值生效
    （``source_platform→"legacy"``、``source_url→None``、``constraints→None``）；必需且无
    默认值的字段（``problem_id``/``title``/``description``/``difficulty``/``test_cases``）
    为 ``None`` 时被省略后仍报 "field required"，失败语义原样保留（并入 missing）。

    Args:
        row: ORM ``api.db.models.Problem`` 行。

    Returns:
        domain ``src.models.Problem``。

    Raises:
        pydantic.ValidationError: ORM 行数据不完整/非法（调用方按不可用并入 missing）。
    """
    data: dict[str, Any] = {
        "problem_id": row.problem_id,
        "title": row.title,
        "description": row.description,
        "difficulty": row.difficulty,
        "tags": row.tags or [],
        "constraints": row.constraints,
        "test_cases": row.test_cases,
        "source_platform": row.source_platform,
        "source_url": row.source_url,
    }
    # NULL 列省略而非显式传 None，使 domain 默认值生效（``tags`` 经 ``or []`` 兜底为
    # ``[]``，不会被过滤）。
    return DomainProblem(**{k: v for k, v in data.items() if v is not None})


def _validation_error_summary(exc: ValidationError) -> str:
    """把 pydantic ``ValidationError`` 压成一行短摘要，避免整段堆栈污染单元失败信息。

    取第一条错误的定位与消息（``field.loc: msg``），多于一条时附加字段计数。
    """
    errors = exc.errors()
    if not errors:
        return "unknown validation error"
    first = errors[0]
    loc = ".".join(str(part) for part in first.get("loc", ())) or "problem"
    summary = f"{loc}: {first.get('msg', 'invalid')}"
    if len(errors) > 1:
        summary += f" (+{len(errors) - 1} more field(s))"
    return summary


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
    from api.files.store import FileStore

    api_key_id = evaluation.api_key_id
    if not api_key_id:
        raise ValueError(f"Credential unavailable: evaluation {evaluation.id} has no api_key_id")

    auth = AuthService(AuthSettings())
    try:
        llm_config = auth.llm_config(api_key_id, evaluation.user_id, model)
    except HTTPException as exc:
        raise ValueError(f"Credential unavailable: {exc.detail}") from None

    store = ProblemStore(session_factory)
    # Uploads are private to their owner and must never be copied into the
    # shared problem table. Prefer the owner's version on ID collisions.
    uploaded = {
        item["problem_id"]: item for item in FileStore(auth.store).dataset(evaluation.user_id)
    }
    problem_map: dict[str, DomainProblem] = {}
    missing: set[str] = set()
    missing_reasons: dict[str, str] = {}
    for pid in evaluation.problem_ids:
        if pid in uploaded:
            try:
                problem_map[pid] = DomainProblem.model_validate(uploaded[pid])
            except ValidationError as exc:
                missing.add(pid)
                missing_reasons[pid] = (
                    f"invalid/incomplete problem data: {_validation_error_summary(exc)}"
                )
            continue
        row = store.get_by_problem_id(pid)
        if row is None:
            missing.add(pid)
            missing_reasons[pid] = "not found in problem store"
            continue
        try:
            problem_map[pid] = _to_domain_problem(row)
        except ValidationError as exc:
            # 数据不完整/非法：按不可用题目处理，不 fail-fast，其单元后续单独失败。
            # 原因与「查不到」区分下传，避免伪装成 not found（verify I-6）。
            missing.add(pid)
            missing_reasons[pid] = (
                f"invalid/incomplete problem data: {_validation_error_summary(exc)}"
            )
    return _EvalContext(
        llm_config=llm_config,
        problem_map=problem_map,
        missing_problems=missing,
        missing_reasons=missing_reasons,
    )


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
        iterations = data.get("iterations")
        metrics = {
            "success": status == "success",
            "failure_category": data.get("failure_category"),
            "failure_mode": data.get("failure_mode"),
            "difficulty": data.get("difficulty"),
            "total_tokens": data.get("total_tokens", 0),
            "execution_time_seconds": data.get("execution_time_seconds", 0.0),
            "cost_usd": meta.get("cost_usd", 0.0),
            "cost_unknown": meta.get("cost_unknown", False),
            "executed_strategy": meta.get("executed_strategy", unit.strategy),
            "cost_downgraded": meta.get("cost_downgraded", False),
            "formal_evaluable": data.get("formal_evaluable", False),
            "quality_metrics": data.get("quality_metrics"),
            "iterations": len(iterations) if isinstance(iterations, list) else 0,
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


# HarnessConfig 要求 dataset_path 必填，但评估单元的题目来自题库（problem_map），
# 从不由 harness 自己加载数据集；该常量只是满足 schema 的占位值，运行时从不被读取。
_UNUSED_DATASET_PATH = "db://evaluations"


def _build_harness(
    ctx: _EvalContext, strategy_names: Iterable[str]
) -> tuple[AlgorithmHarness, dict[str, StrategyConfig], dict[str, tuple[Any, Any]]]:
    """构造评估专用 harness，并为每个策略预建一次 runtime。

    runtime（策略实例 + 沙箱）预建成本高且可跨单元复用，因此按策略各建一次；
    沙箱 preflight 失败或策略名未知时在此 fail-fast（``RuntimeError`` /
    ``ValueError``），而不是等到第一个单元执行时才暴露。

    ``budget_cap_usd`` 显式置 ``None``：预算口径由评估记录（``budget_cap_usd`` +
    ``spent_usd``）经 ``TaskService.pause_when`` 执行，harness 内部预算跟踪器不参与，
    避免出现两个互相冲突的成本闸门。

    Args:
        ctx: 已解析的执行上下文（提供 llm_config）。
        strategy_names: 本次评估需要执行的策略名。

    Returns:
        ``(harness, strategy_configs, runtimes)`` 三元组；``runtimes`` 为
        ``{strategy_name: (strategy_instance, sandbox)}``。
    """
    strategy_configs = {name: StrategyConfig(name=name) for name in strategy_names}
    config = HarnessConfig(
        llm_config=ctx.llm_config,
        sandbox_config=SandboxConfig(),
        dataset_path=_UNUSED_DATASET_PATH,
        strategies=list(strategy_configs.values()),
        budget_cap_usd=None,
        enable_quality_analysis=False,
    )
    harness = AlgorithmHarness(config)
    runtimes = {
        name: harness._prepare_strategy_runtime(strategy_config)
        for name, strategy_config in strategy_configs.items()
    }
    return harness, strategy_configs, runtimes


def _make_worker(
    harness: AlgorithmHarness,
    strategy_configs: dict[str, StrategyConfig],
    runtimes: dict[str, tuple[Any, Any]],
    problem_map: dict[str, DomainProblem],
    missing_reasons: dict[str, str] | None = None,
    *,
    execution_strategies: dict[str, str] | None = None,
) -> Callable[[TaskUnit], ExecutionResult]:
    """返回真实执行一个 TaskUnit 的 worker 闭包。

    闭包只捕获 harness、策略配置、预建 runtime 与只读题目映射——**绝不捕获 db
    会话**：worker 运行在 TaskService 的 executor 线程，跨线程触碰 SQLAlchemy
    session 会损坏连接状态；所有落库都在主线程的回调里完成。

    cost 走 harness 的真实定价口径：无定价信息时 ``cost_usd`` 为 0.0 且
    ``cost_unknown`` 置 True（诚实口径，不伪造花费）。

    Args:
        harness: 已构造的 AlgorithmHarness。
        strategy_configs: ``{strategy_name: StrategyConfig}``。
        runtimes: ``{strategy_name: (strategy_instance, sandbox)}``。
        problem_map: ``{problem_id: Problem}``，题库命中的题目。
        missing_reasons: ``{problem_id: 不可用原因}``；当单元题目不在 problem_map
            时用它拼接真实原因（缺失 vs 非法）。缺省或无对应键时回退
            ``"not found in problem store"``。

    Returns:
        ``worker(unit) -> ExecutionResult``。

    Raises:
        ValueError: 单元对应的题目不可用时（worker 调用时抛出），原因取自
            ``missing_reasons``，区分「查不到」与「数据非法」。
    """
    reasons = missing_reasons or {}

    def worker(unit: TaskUnit) -> ExecutionResult:
        """真实执行一个单元，并把真实 cost 写入 ``result.metadata``。"""
        problem = problem_map.get(unit.problem_id)
        if problem is None:
            raise ValueError(
                f"Problem {unit.problem_id}: "
                f"{reasons.get(unit.problem_id, 'not found in problem store')}"
            )
        selected = (execution_strategies or {}).get(unit.unit_id, unit.strategy)
        strategy_config = strategy_configs[selected]
        strategy, sandbox = runtimes[selected]
        result = harness._execute_problem(strategy_config, problem, strategy, sandbox)
        result.metadata["executed_strategy"] = selected
        result.metadata["cost_downgraded"] = selected != unit.strategy
        cost, pricing_metadata = harness._estimate_cost([result])
        result.metadata["cost_usd"] = cost
        result.metadata["cost_unknown"] = bool(
            pricing_metadata.get("unknown_usage") or pricing_metadata.get("unknown_pricing")
        )
        return result

    return worker
