"""Celery 任务单元测试

测试 run_evaluation_task 的核心功能，包括任务生命周期管理、进度报告和错误处理。
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Evaluation, EvaluationResult
from api.db.models import Problem as ORMProblem
from src.harness import AlgorithmHarness
from src.models import ExecutionResult, LLMConfig, Problem
from src.models import Problem as DomainProblem
from src.task_service import TaskService, TaskUnit
from src.tasks.evaluation import run_evaluation_task


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
def evaluation_setup(db_session):
    """创建测试用的 Evaluation 和 AsyncTask 记录"""
    evaluation_id = str(uuid.uuid4())
    user_id = "test_user"

    # 创建 AsyncTask
    async_task = AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id="celery-123",
        task_type="evaluation",
        entity_id=evaluation_id,
        user_id=user_id,
        status="pending",
    )
    db_session.add(async_task)

    # 创建 Evaluation
    evaluation = Evaluation(
        id=evaluation_id,
        user_id=user_id,
        status="pending",
        strategy_names=["strategy_a"],
        problem_ids=["problem_1"],
        problem_count=1,
        async_task_id=async_task.id,
    )
    db_session.add(evaluation)
    db_session.commit()

    return {
        "evaluation_id": evaluation_id,
        "user_id": user_id,
        "async_task_id": async_task.id,
        "evaluation": evaluation,
        "async_task": async_task,
    }


class TestRunEvaluationTask:
    """测试 run_evaluation_task 核心功能"""

    def test_run_evaluation_task_success(self, db_session, evaluation_setup):
        """验证任务成功执行完整流程"""
        evaluation_id = evaluation_setup["evaluation_id"]

        # Mock TaskManager
        with patch("src.tasks.evaluation.TaskManager") as MockTaskManager:
            mock_task_manager = Mock()
            MockTaskManager.return_value = mock_task_manager

            # Mock TaskService
            with patch("src.tasks.evaluation.TaskService") as MockTaskService:
                mock_task_service = Mock()
                MockTaskService.return_value = mock_task_service

                # Mock TaskService.create 返回一个模拟的 TaskRecord
                mock_record = Mock()
                mock_record.run_id = "test-run-id"
                mock_record.state = "completed"
                mock_record.completed_units = 1
                mock_record.total_units = 1
                mock_task_service.create.return_value = mock_record
                mock_task_service.run.return_value = mock_record
                mock_task_service.get.side_effect = FileNotFoundError()

                # Mock database session
                with (
                    patch("src.tasks.evaluation.get_db_session") as mock_get_db,
                    patch("src.tasks.evaluation._resolve_execution_context") as mock_ctx,
                    patch("src.tasks.evaluation._build_harness") as mock_build,
                ):
                    mock_get_db.return_value = db_session
                    # 这些用例聚焦编排 + 终态映射（TaskService 已 mock），短路真实
                    # 凭证/题目解析与 harness 构造（避免触网 / 起 docker）。
                    mock_ctx.return_value = Mock(problem_map={})
                    mock_build.return_value = (Mock(), {}, {})

                    # When: 执行任务
                    result = run_evaluation_task(evaluation_id)

        # Then: 返回正确的结果
        assert result["evaluation_id"] == evaluation_id
        assert result["status"] == "completed"
        assert result["completed_units"] == 1
        assert result["total_units"] == 1

    def test_run_evaluation_task_evaluation_not_found(self, db_session):
        """验证评估不存在时抛出 ValueError"""
        evaluation_id = "non-existent-id"

        with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
            mock_get_db.return_value = db_session

            # When/Then: 执行任务应该抛出 ValueError
            with pytest.raises(ValueError, match="Evaluation .* not found"):
                run_evaluation_task(evaluation_id)

    def test_run_evaluation_task_empty_strategies(self, db_session, evaluation_setup):
        """验证 strategy_names 为空时抛出 ValueError"""
        evaluation_id = evaluation_setup["evaluation_id"]
        evaluation = evaluation_setup["evaluation"]
        evaluation.strategy_names = []
        db_session.commit()

        with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
            mock_get_db.return_value = db_session

            # When/Then: 执行任务应该抛出 ValueError
            with pytest.raises(ValueError, match="strategy_names cannot be empty"):
                run_evaluation_task(evaluation_id)

    def test_run_evaluation_task_empty_problems(self, db_session, evaluation_setup):
        """验证 problem_ids 为空时抛出 ValueError"""
        evaluation_id = evaluation_setup["evaluation_id"]
        evaluation = evaluation_setup["evaluation"]
        evaluation.problem_ids = []
        db_session.commit()

        with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
            mock_get_db.return_value = db_session

            # When/Then: 执行任务应该抛出 ValueError
            with pytest.raises(ValueError, match="problem_ids cannot be empty"):
                run_evaluation_task(evaluation_id)

    def test_run_evaluation_task_paused_state(self, db_session, evaluation_setup):
        """验证任务暂停状态正确处理"""
        evaluation_id = evaluation_setup["evaluation_id"]

        with patch("src.tasks.evaluation.TaskManager") as MockTaskManager:
            mock_task_manager = Mock()
            MockTaskManager.return_value = mock_task_manager

            with patch("src.tasks.evaluation.TaskService") as MockTaskService:
                mock_task_service = Mock()
                MockTaskService.return_value = mock_task_service

                # 模拟暂停状态
                mock_record = Mock()
                mock_record.run_id = "test-run-id"
                mock_record.state = "paused"
                mock_record.completed_units = 1
                mock_record.total_units = 2
                mock_task_service.create.return_value = mock_record
                mock_task_service.run.return_value = mock_record
                mock_task_service.get.side_effect = FileNotFoundError()

                with (
                    patch("src.tasks.evaluation.get_db_session") as mock_get_db,
                    patch("src.tasks.evaluation._resolve_execution_context") as mock_ctx,
                    patch("src.tasks.evaluation._build_harness") as mock_build,
                ):
                    mock_get_db.return_value = db_session
                    # 这些用例聚焦编排 + 终态映射（TaskService 已 mock），短路真实
                    # 凭证/题目解析与 harness 构造（避免触网 / 起 docker）。
                    mock_ctx.return_value = Mock(problem_map={})
                    mock_build.return_value = (Mock(), {}, {})

                    # When: 执行任务
                    result = run_evaluation_task(evaluation_id)

        # Then: 返回暂停状态
        assert result["status"] == "paused"
        assert result["completed_units"] == 1
        assert result["total_units"] == 2

    def test_run_evaluation_task_resume_from_paused(self, db_session, evaluation_setup):
        """验证从暂停状态恢复任务"""
        evaluation_id = evaluation_setup["evaluation_id"]

        with patch("src.tasks.evaluation.TaskManager") as MockTaskManager:
            mock_task_manager = Mock()
            MockTaskManager.return_value = mock_task_manager

            with patch("src.tasks.evaluation.TaskService") as MockTaskService:
                mock_task_service = Mock()
                MockTaskService.return_value = mock_task_service

                # 模拟已存在的暂停任务
                existing_record = Mock()
                existing_record.state = "paused"
                mock_task_service.get.return_value = existing_record

                # 恢复后完成
                completed_record = Mock()
                completed_record.run_id = "test-run-id"
                completed_record.state = "completed"
                completed_record.completed_units = 2
                completed_record.total_units = 2
                mock_task_service.run.return_value = completed_record

                with (
                    patch("src.tasks.evaluation.get_db_session") as mock_get_db,
                    patch("src.tasks.evaluation._resolve_execution_context") as mock_ctx,
                    patch("src.tasks.evaluation._build_harness") as mock_build,
                ):
                    mock_get_db.return_value = db_session
                    # 这些用例聚焦编排 + 终态映射（TaskService 已 mock），短路真实
                    # 凭证/题目解析与 harness 构造（避免触网 / 起 docker）。
                    mock_ctx.return_value = Mock(problem_map={})
                    mock_build.return_value = (Mock(), {}, {})

                    # When: 执行任务
                    result = run_evaluation_task(evaluation_id)

        # Then: 任务完成
        assert result["status"] == "completed"
        assert result["completed_units"] == 2

        # 验证使用了 resume=True
        assert mock_task_service.run.call_args.kwargs["resume"] is True


class TestCreateTaskUnits:
    """测试 _create_task_units 辅助函数"""

    def test_create_task_units_single_strategy_single_problem(self):
        """验证单个策略和单个问题生成一个单元"""
        from src.tasks.evaluation import _create_task_units

        units = _create_task_units(["strategy_a"], ["problem_1"])

        assert len(units) == 1
        assert units[0].strategy == "strategy_a"
        assert units[0].problem_id == "problem_1"
        assert units[0].repeat_index == 0

    def test_create_task_units_multiple_strategies_multiple_problems(self):
        """验证多个策略和多个问题生成笛卡尔积"""
        from src.tasks.evaluation import _create_task_units

        units = _create_task_units(
            ["strategy_a", "strategy_b"], ["problem_1", "problem_2", "problem_3"]
        )

        # 2 策略 × 3 问题 = 6 单元
        assert len(units) == 6

        # 验证笛卡尔积
        strategies = [u.strategy for u in units]
        problems = [u.problem_id for u in units]

        assert strategies.count("strategy_a") == 3
        assert strategies.count("strategy_b") == 3
        assert problems.count("problem_1") == 2
        assert problems.count("problem_2") == 2
        assert problems.count("problem_3") == 2


@pytest.fixture
def session_factory():
    """返回绑定内存库的 sessionmaker（ProblemStore 构造入参）。"""
    engine = create_engine("sqlite:///:memory:")
    return sessionmaker(bind=engine)


@pytest.fixture
def make_evaluation():
    """构造未持久化的 Evaluation 实例，字段可覆盖。"""

    def _make(**overrides):
        params = {
            "id": str(uuid.uuid4()),
            "user_id": "test_user",
            "model": "test-model",
            "api_key_id": "key-1",
            "problem_ids": ["p1"],
            "strategy_names": ["strategy_a"],
        }
        params.update(overrides)
        return Evaluation(**params)

    return _make


class TestResolveExecutionContext:
    """测试 _resolve_execution_context fail-fast 解析（model + 凭证 + 题目）。

    凭证与题目均通过 mock/fake 隔离，绝不发起在线调用或真实凭证解密。
    """

    def test_missing_model_fails_fast(self, make_evaluation, session_factory):
        """model 缺失时立即抛 ValueError（含 'no model'）。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model=None)
        with pytest.raises(ValueError, match="no model"):
            _resolve_execution_context(ev, session_factory)

    def test_missing_api_key_fails_fast(self, make_evaluation, session_factory):
        """api_key_id 缺失时在解密前 fail-fast（含 'Credential unavailable'）。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model="m", api_key_id=None)
        with (
            patch("api.auth.config.AuthSettings"),
            patch("api.auth.service.AuthService") as MockAuth,
        ):
            MockAuth.return_value.llm_config.side_effect = AssertionError(
                "llm_config must not be reached without an api_key_id"
            )
            with pytest.raises(ValueError, match="Credential unavailable"):
                _resolve_execution_context(ev, session_factory)

    def test_credential_unresolvable_fails_fast(self, make_evaluation, session_factory):
        """凭证不可解析时把 HTTPException 转成 ValueError（含 'Credential unavailable'）。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model="m", api_key_id="bad")
        with (
            patch("api.auth.config.AuthSettings"),
            patch("api.auth.service.AuthService") as MockAuth,
        ):
            MockAuth.return_value.llm_config.side_effect = HTTPException(403, "nope")
            with pytest.raises(ValueError, match="Credential unavailable"):
                _resolve_execution_context(ev, session_factory)

    def test_missing_problem_recorded_not_fatal(self, make_evaluation, session_factory):
        """题目缺失记入 missing_problems；命中的 ORM 行转成 domain Problem 入 problem_map。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model="m", problem_ids=["p1", "missing"])
        sentinel_llm = object()
        orm_row = ORMProblem(
            id="row-1",
            problem_id="p1",
            title="Two Sum",
            description="Return indices of the two numbers that add up to the target.",
            difficulty="easy",
            tags=["array"],
            constraints=None,
            test_cases=[{"input": {"nums": [2, 7], "target": 9}, "expected_output": [0, 1]}],
            # 真实落库形状：data/problems.json 无 source_platform/source_url 键 → 列为 NULL
            source_platform=None,
            source_url=None,
        )

        class _FakeStore:
            def __init__(self, _session_factory):
                pass

            def get_by_problem_id(self, problem_id):
                return orm_row if problem_id == "p1" else None

        with (
            patch("api.auth.config.AuthSettings"),
            patch("api.auth.service.AuthService") as MockAuth,
        ):
            MockAuth.return_value.llm_config.return_value = sentinel_llm
            with patch("api.db.problem_store.ProblemStore", _FakeStore):
                ctx = _resolve_execution_context(ev, session_factory)

        assert ctx.llm_config is sentinel_llm
        assert "missing" in ctx.missing_problems
        assert "p1" in ctx.problem_map
        # ORM 行必须被转换成 domain src.models.Problem（供 _execute_problem 消费）
        converted = ctx.problem_map["p1"]
        assert isinstance(converted, DomainProblem)
        assert converted.public_test_cases
        assert converted.hidden_test_cases == []
        assert converted.migration_status == "legacy_test_cases_as_public"
        # ORM 列为 NULL 时省略该键 → domain 默认值生效（非 Optional 字段不接受显式 None）
        assert converted.source_platform == "legacy"
        assert converted.source_url is None

    def test_invalid_problem_row_recorded_as_missing(self, make_evaluation, session_factory):
        """ORM 行数据非法（description 短于 min_length=10）→ ValidationError → 并入 missing。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model="m", problem_ids=["bad"])
        bad_row = ORMProblem(
            id="row-2",
            problem_id="bad",
            title="Bad",
            description="",  # 短于 domain Problem.description 的 min_length=10
            difficulty="easy",
            tags=[],
            constraints=None,
            test_cases=[{"input": {"x": 1}, "expected_output": 1}],
            source_platform=None,
            source_url=None,
        )

        class _FakeStore:
            def __init__(self, _session_factory):
                pass

            def get_by_problem_id(self, problem_id):
                return bad_row

        with (
            patch("api.auth.config.AuthSettings"),
            patch("api.auth.service.AuthService") as MockAuth,
        ):
            MockAuth.return_value.llm_config.return_value = object()
            with patch("api.db.problem_store.ProblemStore", _FakeStore):
                ctx = _resolve_execution_context(ev, session_factory)

        assert "bad" in ctx.missing_problems
        assert "bad" not in ctx.problem_map


@pytest.fixture
def make_unit():
    """构造 TaskUnit 实例，字段可覆盖（默认已完成单元）。"""

    def _make(**overrides):
        params = {
            "unit_id": str(uuid.uuid4()),
            "strategy": "strategy_a",
            "problem_id": "problem_1",
            "repeat_index": 0,
            "status": "completed",
        }
        params.update(overrides)
        return TaskUnit(**params)

    return _make


class TestRecordUnitResult:
    """测试 _record_unit_result 逐单元映射 + 幂等 upsert + 返回 cost。

    计数聚合（completed_count/failed_count）归 Task 6 的 on_unit_finished，
    本 helper 不设置 evaluation 计数，故此处不断言计数。
    """

    def test_record_completed_unit_upserts_and_counts(
        self, db_session, evaluation_setup, make_unit
    ):
        """完成单元写入 success 行 + metrics + 返回 cost；同键二次调用不新增行。"""
        from src.tasks.evaluation import _record_unit_result

        evaluation = evaluation_setup["evaluation"]
        unit = make_unit(
            problem_id="problem_1",
            strategy="strategy_a",
            status="completed",
            result={
                "status": "success",
                "total_tokens": 10,
                "execution_time_seconds": 1.5,
                "metadata": {"cost_usd": 0.01, "cost_unknown": False},
            },
        )

        cost = _record_unit_result(db_session, evaluation, unit)

        row = (
            db_session.query(EvaluationResult)
            .filter_by(
                evaluation_id=evaluation.id,
                problem_id=unit.problem_id,
                strategy_name=unit.strategy,
            )
            .one()
        )
        assert row.status == "success"
        assert row.metrics["total_tokens"] == 10
        assert row.metrics["success"] is True
        assert row.metrics["cost_usd"] == 0.01
        assert cost == 0.01

        # 同键二次调用不新增行
        _record_unit_result(db_session, evaluation, unit)
        assert db_session.query(EvaluationResult).count() == 1

    def test_record_failed_unit_writes_failed_row(self, db_session, evaluation_setup, make_unit):
        """失败单元写入 status='failed' 行、error_message 含原因、cost==0.0。"""
        from src.tasks.evaluation import _record_unit_result

        evaluation = evaluation_setup["evaluation"]
        unit = make_unit(
            status="failed",
            result=None,
            error="Problem x not found in problem store",
        )

        cost = _record_unit_result(db_session, evaluation, unit)

        row = db_session.query(EvaluationResult).one()
        assert row.status == "failed"
        assert row.metrics is None
        assert "not found" in row.error_message
        assert cost == 0.0


@pytest.fixture
def eval_ctx():
    """构造 _EvalContext：占位凭证 + 一道真实 domain Problem。

    ``api_key`` 为假值；真实 LLMClient 构造发生在 ``_prepare_strategy_runtime``
    内部，测试中已被 patch，因此绝不发起在线调用。
    """
    from src.tasks.evaluation import _EvalContext

    llm_config = LLMConfig(
        provider="openai", api_key=SecretStr("sk-placeholder"), model="test-model"
    )
    problem = Problem(
        problem_id="p1",
        title="Two Sum",
        description="Return indices of the two numbers that add up to the target.",
        difficulty="easy",
        public_test_cases=[{"input": {"nums": [2, 7], "target": 9}, "expected_output": [0, 1]}],
        hidden_test_cases=[{"input": {"nums": [3, 2], "target": 5}, "expected_output": [0, 1]}],
    )
    return _EvalContext(
        llm_config=llm_config,
        problem_map={"p1": problem},
        missing_problems=set(),
    )


@pytest.fixture
def harness_ctx(eval_ctx):
    """调用真实 _build_harness，但屏蔽 runtime 预建（禁 docker / 禁网）。

    返回 ``((harness, strategy_configs, runtimes), prepare_mock)``。
    """
    from src.tasks.evaluation import _build_harness

    forbidden = AssertionError("runtime pre-build must not touch sandbox or LLM client")
    prepare = Mock(return_value=(object(), object()))
    with (
        patch.object(AlgorithmHarness, "_prepare_strategy_runtime", prepare),
        patch("src.harness.SandboxExecutor", side_effect=forbidden),
        patch("src.harness.LLMClient", side_effect=forbidden),
    ):
        built = _build_harness(eval_ctx, ["vanilla", "chain_of_thought"])
    return built, prepare


class TestBuildHarness:
    """测试 _build_harness：诚实的 HarnessConfig + 每策略一次 runtime 预建。"""

    def test_build_harness_prepares_runtime_once_per_strategy(self, eval_ctx, harness_ctx):
        """配置不伪造预算/数据集，且每个策略各预建一次 runtime。"""
        from src.tasks.evaluation import _UNUSED_DATASET_PATH

        (harness, strategy_configs, runtimes), prepare = harness_ctx

        assert isinstance(harness, AlgorithmHarness)
        assert harness.config.llm_config is eval_ctx.llm_config
        assert harness.config.dataset_path == _UNUSED_DATASET_PATH
        assert harness.config.budget_cap_usd is None
        assert harness.config.enable_quality_analysis is False
        assert harness.budget_tracker is None

        assert list(strategy_configs) == ["vanilla", "chain_of_thought"]
        assert [sc.name for sc in strategy_configs.values()] == [
            "vanilla",
            "chain_of_thought",
        ]
        assert harness.config.strategies == list(strategy_configs.values())

        # 每策略恰好一次，且传入的是对应 StrategyConfig
        assert prepare.call_count == len(strategy_configs)
        assert [call.args[0] for call in prepare.call_args_list] == list(strategy_configs.values())

        assert set(runtimes) == set(strategy_configs)
        for name in strategy_configs:
            assert runtimes[name] is prepare.return_value


class TestMakeWorker:
    """测试 _make_worker 返回的真实 worker 闭包（不引用 db / session）。"""

    def test_worker_returns_real_result_with_cost(
        self, monkeypatch, eval_ctx, harness_ctx, make_unit
    ):
        """worker 走 harness 真实执行路径并把真实 cost 写入 result.metadata。"""
        from src.tasks.evaluation import _make_worker

        (harness, strategy_configs, runtimes), _prepare = harness_ctx
        seen: dict[str, tuple] = {}

        def fake_execute(strategy_config, problem, strategy, sandbox):
            seen["args"] = (strategy_config, problem, strategy, sandbox)
            return ExecutionResult(
                problem_id=problem.problem_id,
                strategy=strategy_config.name,
                generated_code="def solution(**kw):\n    return 1",
                status="success",
            )

        monkeypatch.setattr(harness, "_execute_problem", fake_execute)
        monkeypatch.setattr(
            harness,
            "_estimate_cost",
            lambda results: (0.02, {"unknown_usage": False, "unknown_pricing": False}),
        )

        worker = _make_worker(harness, strategy_configs, runtimes, eval_ctx.problem_map)
        result = worker(make_unit(strategy="vanilla", problem_id="p1"))

        assert isinstance(result, ExecutionResult)
        assert result.status == "success"
        assert result.problem_id == "p1"
        assert result.strategy == "vanilla"
        assert result.metadata["cost_usd"] == 0.02
        assert result.metadata["cost_unknown"] is False

        # 真实 runtime 被复用（每策略一次预建），不重新构造
        assert seen["args"][0] is strategy_configs["vanilla"]
        assert seen["args"][1] is eval_ctx.problem_map["p1"]
        assert seen["args"][2:] == runtimes["vanilla"]

    def test_worker_missing_problem_raises(self, eval_ctx, harness_ctx, make_unit):
        """题库缺失的单元由 worker 抛出可审计的 ValueError。"""
        from src.tasks.evaluation import _make_worker

        (harness, strategy_configs, runtimes), _prepare = harness_ctx
        worker = _make_worker(harness, strategy_configs, runtimes, eval_ctx.problem_map)

        with pytest.raises(ValueError, match="not found in problem store"):
            worker(make_unit(strategy="vanilla", problem_id="ghost"))

    def test_worker_surfaces_invalid_row_reason(self, eval_ctx, harness_ctx, make_unit):
        """I-6：非法行（ValidationError）的原因经 missing_reasons 下传，不再伪装成 not found。

        修复前 ``_make_worker`` 无第 5 个参数 → 传 5 参抛 TypeError，本用例失败（RED）。
        """
        from src.tasks.evaluation import _make_worker

        (harness, strategy_configs, runtimes), _prepare = harness_ctx
        worker = _make_worker(
            harness,
            strategy_configs,
            runtimes,
            eval_ctx.problem_map,
            {"p_bad": "invalid/incomplete problem data: description: String too short"},
        )

        with pytest.raises(ValueError, match="invalid/incomplete problem data"):
            worker(make_unit(strategy="vanilla", problem_id="p_bad"))

    def test_worker_missing_row_still_reports_not_found(self, eval_ctx, harness_ctx, make_unit):
        """I-6 防回归：真缺失（row is None）单元仍报 not found in problem store。"""
        from src.tasks.evaluation import _make_worker

        (harness, strategy_configs, runtimes), _prepare = harness_ctx
        worker = _make_worker(
            harness,
            strategy_configs,
            runtimes,
            eval_ctx.problem_map,
            {"ghost": "not found in problem store"},
        )

        with pytest.raises(ValueError, match="not found in problem store"):
            worker(make_unit(strategy="vanilla", problem_id="ghost"))


# ---------------------------------------------------------------------------
# Task 6: run_evaluation_task 真实执行集成测试（不触网、不起 docker、不 mock TaskService）
# ---------------------------------------------------------------------------


class _HarnessControl:
    """集成测试中对 harness 替身行为的可调控制。"""

    def __init__(self):
        self.cost = 0.01
        self.cost_meta = {"unknown_usage": False, "unknown_pricing": False}
        self.execute_status = "success"
        self.execute_calls: list[tuple[str, str]] = []


@pytest.fixture
def integration_harness(monkeypatch, tmp_path):
    """patch harness 执行/定价/runtime 与 celery update_state，并隔离 TaskService 文件写入。

    TaskService 用相对 ``root=f"data/tasks/{id}"``，chdir 到 tmp_path 隔离产物；
    worker 真实跑在 executor 线程但只读 problem_map/harness 替身，不触碰 db。
    """
    control = _HarnessControl()
    monkeypatch.chdir(tmp_path)

    def fake_prepare(self, strategy_config):
        return (object(), object())

    def fake_execute(self, strategy_config, problem, strategy, sandbox):
        control.execute_calls.append((strategy_config.name, problem.problem_id))
        return ExecutionResult(
            problem_id=problem.problem_id,
            strategy=strategy_config.name,
            generated_code="def solution(**kw):\n    return 1",
            status=control.execute_status,
            total_tokens=10,
            execution_time_seconds=0.5,
            difficulty="easy",
        )

    def fake_estimate(self, results):
        return (control.cost, control.cost_meta)

    monkeypatch.setattr(AlgorithmHarness, "_prepare_strategy_runtime", fake_prepare)
    monkeypatch.setattr(AlgorithmHarness, "_execute_problem", fake_execute)
    monkeypatch.setattr(AlgorithmHarness, "_estimate_cost", fake_estimate)
    monkeypatch.setattr(run_evaluation_task, "update_state", lambda *a, **k: None)
    return control


@pytest.fixture
def auth_ok():
    """patch AuthService 返回合法 LLMConfig（不触网、不解密真实凭证）。"""
    llm = LLMConfig(provider="openai", api_key=SecretStr("sk-test"), model="test-model")
    with (
        patch("api.auth.config.AuthSettings"),
        patch("api.auth.service.AuthService") as MockAuth,
    ):
        MockAuth.return_value.llm_config.return_value = llm
        yield llm


@pytest.fixture
def auth_bad():
    """patch AuthService.llm_config 抛 HTTPException（凭证不可解析）。"""
    with (
        patch("api.auth.config.AuthSettings"),
        patch("api.auth.service.AuthService") as MockAuth,
    ):
        MockAuth.return_value.llm_config.side_effect = HTTPException(403, "nope")
        yield


def _seed_problem(db, problem_id):
    """seed 一行真实 ORM Problem（让 _resolve_execution_context + 转换真实跑通）。"""
    db.add(
        ORMProblem(
            id=str(uuid.uuid4()),
            problem_id=problem_id,
            title=f"Title {problem_id}",
            description="Return indices of the two numbers that add up to the target.",
            difficulty="easy",
            tags=["array"],
            constraints=None,
            test_cases=[{"input": {"nums": [2, 7], "target": 9}, "expected_output": [0, 1]}],
            # 真实导入形状：data/problems.json 的记录不含 source_platform/source_url
            # 键，导入后 ORM 列为 NULL，seed 必须与之一致（否则掩盖转换缺陷）。
            source_platform=None,
            source_url=None,
        )
    )


def _seed_evaluation(
    db, *, problem_ids, strategy_names, budget_cap_usd=None, seed_problem_ids=None
):
    """seed Evaluation + AsyncTask + 对应 ORM Problem 行并 commit，返回 evaluation_id。

    ``seed_problem_ids`` 默认与 ``problem_ids`` 相同；显式传入其子集可模拟「题库中
    缺失部分题目」（评估声明了 problem_id，但库里没有对应 ORM 行）。
    """
    evaluation_id = str(uuid.uuid4())
    async_task = AsyncTask(
        id=str(uuid.uuid4()),
        celery_task_id=f"celery-{evaluation_id}",
        task_type="evaluation",
        entity_id=evaluation_id,
        user_id="test_user",
        status="pending",
    )
    db.add(async_task)
    db.add(
        Evaluation(
            id=evaluation_id,
            user_id="test_user",
            status="pending",
            model="test-model",
            api_key_id="key-1",
            strategy_names=strategy_names,
            problem_ids=problem_ids,
            problem_count=len(problem_ids),
            budget_cap_usd=budget_cap_usd,
            async_task_id=async_task.id,
        )
    )
    for pid in problem_ids if seed_problem_ids is None else seed_problem_ids:
        _seed_problem(db, pid)
    db.commit()
    return evaluation_id


def _reload(db, model, id_):
    db.expunge_all()
    return db.query(model).filter_by(id=id_).first()


class TestRunEvaluationTaskIntegration:
    """run_evaluation_task 经真实 TaskService 编排 + 真实 harness 执行路径的集成测试。"""

    def test_run_evaluation_task_completes_all_units(
        self, db_session, integration_harness, auth_ok
    ):
        """多单元全 success → completed、计数正确、每单元一行真实结果、spent_usd>0、无 mock。"""
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla", "chain_of_thought"],
        )
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        assert ev.status == "completed"
        assert ev.completed_count == 4
        assert ev.failed_count == 0
        assert db_session.query(EvaluationResult).count() == 4
        assert ev.spent_usd > 0
        assert result["status"] == "completed"
        assert result["completed_units"] == 4
        # 真实执行路径：4 个单元都经 harness._execute_problem
        assert len(integration_harness.execute_calls) == 4
        # 结果不含 mock，度量来自真实 ExecutionResult
        for row in db_session.query(EvaluationResult).all():
            assert row.status == "success"
            assert row.metrics["total_tokens"] == 10
            assert "mock" not in row.metrics

    def test_run_evaluation_task_credential_failure_no_results(
        self, db_session, integration_harness, auth_bad
    ):
        """凭证不可解析 → ValueError、evaluation.status=failed、无任何 EvaluationResult 行。"""
        evaluation_id = _seed_evaluation(db_session, problem_ids=["p1"], strategy_names=["vanilla"])
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            with pytest.raises(ValueError):
                run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        assert ev.status == "failed"
        assert db_session.query(EvaluationResult).count() == 0
        assert integration_harness.execute_calls == []

    def test_run_evaluation_task_budget_pause(self, db_session, integration_harness, auth_ok):
        """budget_cap_usd 小于首单元 cost → 首单元后触顶 paused、未开始单元不执行。"""
        integration_harness.cost = 0.05
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
            budget_cap_usd=0.03,
        )
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        assert ev.status == "paused"
        assert ev.completed_count < 2
        assert result["status"] == "paused"
        # 严格在完成单元边界停止：仅首单元真实执行
        assert len(integration_harness.execute_calls) == 1

    def test_run_evaluation_task_unknown_pricing_honest(
        self, db_session, integration_harness, auth_ok
    ):
        """成本无定价 → spent_usd 不伪造增长、不触发预算暂停、结果行 cost_unknown=True。"""
        integration_harness.cost = 0.0
        integration_harness.cost_meta = {"unknown_usage": True}
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
            budget_cap_usd=0.01,  # 有 cap，但 cost 未知不伪造 → 不触发暂停
        )
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        assert ev.spent_usd == 0.0
        assert ev.status == "completed"
        assert result["status"] == "completed"
        rows = db_session.query(EvaluationResult).all()
        assert len(rows) == 2
        for row in rows:
            assert row.metrics["cost_unknown"] is True
            assert row.metrics["cost_usd"] == 0.0

    def test_resume_after_pause_runs_only_remaining(self, db_session, integration_harness, auth_ok):
        """预算触顶 paused 后提高预算 resume：只跑剩余单元、不重复已完成单元。

        断言终态 completed、计数覆盖全部单元、EvaluationResult 无重复行、
        spent_usd 续增不重置，且每个单元经 harness 恰好真实执行一次。
        """
        # 首单元 cost=0.05 > budget_cap_usd=0.03 → 首单元后触顶 paused（仿 budget_pause）
        integration_harness.cost = 0.05
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
            budget_cap_usd=0.03,
        )
        total_units = 2  # 1 策略 × 2 题目

        # 第一次执行：预算触顶 → paused，仅完成首单元
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            first_result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        assert ev.status == "paused"
        assert first_result["status"] == "paused"
        first_done = ev.completed_count
        first_spent = ev.spent_usd
        assert first_done < total_units
        assert len(integration_harness.execute_calls) == 1  # 仅首单元真实执行

        # 提高预算，使 resume 后剩余单元不再触顶
        ev.budget_cap_usd = 10.0
        db_session.commit()

        # 第二次执行：resume（TaskService 保留 terminal 单元，只跑剩余 queued 单元）
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            second_result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        # 终态：正常路径应为 completed
        assert ev.status in ("completed", "failed")
        assert second_result["status"] == "completed"
        # 计数覆盖全部单元（基于 record.units 全量重算，不重置）
        assert ev.completed_count + ev.failed_count == total_units
        assert ev.completed_count >= first_done
        # 无重复行：每单元恰好一行 EvaluationResult（upsert 幂等）
        assert db_session.query(EvaluationResult).count() == total_units
        # spent_usd 续增不重置
        assert ev.spent_usd > first_spent
        # resume 未重跑已完成单元：每单元经 harness 恰好真实执行一次
        calls = integration_harness.execute_calls
        assert len(calls) == len(set(calls)) == total_units
        assert set(calls) == {("vanilla", "p1"), ("vanilla", "p2")}

    def test_run_evaluation_task_missing_problem_fails_only_that_unit(
        self, db_session, integration_harness, auth_ok
    ):
        """部分题目缺失（Design §8 #4）+ 聚合口径（§8 #10）：缺失单元 failed，其余继续。

        评估声明 2 道题但只 seed 1 道：p_missing 经 ``_resolve_execution_context``
        进入 ``missing_problems``，worker 执行时抛 ValueError → TaskService 标该单元
        failed；p_exist 单元照常 success。执行不整体中止（其余单元照跑、结果全部落库），
        终态因 TaskService 的「非全部 completed 即 failed」口径而为 failed。
        """
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p_exist", "p_missing"],
            strategy_names=["vanilla"],
            seed_problem_ids=["p_exist"],  # p_missing 不在题库（模拟查不到）
        )
        total_units = 2  # 1 策略 × 2 题目
        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            result = run_evaluation_task(evaluation_id)

        ev = _reload(db_session, Evaluation, evaluation_id)
        # 聚合口径：completed + failed == 单元总数，不因部分失败而丢计数
        assert ev.completed_count == 1
        assert ev.failed_count == 1
        assert ev.completed_count + ev.failed_count == total_units
        # 每单元一行：缺失单元也落库并标 failed（不静默跳过）
        rows = db_session.query(EvaluationResult).all()
        assert len(rows) == total_units
        missing_row = next(r for r in rows if r.problem_id == "p_missing")
        ok_row = next(r for r in rows if r.problem_id == "p_exist")
        assert missing_row.status == "failed"
        assert "not found" in (missing_row.error_message or "")
        assert ok_row.status == "success"
        # 不整体中止：存在题目的单元仍然真实执行，且缺失单元不会阻断调度
        assert integration_harness.execute_calls == [("vanilla", "p_exist")]
        # 评估终态：TaskService 把「有单元未 completed」的 run 定为 failed（而非中止），
        # 因此部分题目缺失的评估以 failed 收尾，但已完成单元的计数与结果行全部保留。
        assert ev.status == "failed"
        assert result["status"] == "failed"
        assert result["completed_units"] == total_units
        assert result["total_units"] == total_units

    def test_run_evaluation_task_records_percentage_and_current_step(
        self, integration_harness, auth_ok, monkeypatch, tmp_path
    ):
        """单元开始前写入百分比和当前步骤，执行中可从任务记录读到。"""
        db_file = tmp_path / "progress.sqlite3"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        evaluation_id = _seed_evaluation(
            db,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
        )
        for row in db.query(ORMProblem).all():
            row.description = "hidden problem body that must stay out of the step"
        db.commit()

        seen: list[dict] = []
        metas: list[dict] = []
        reader = sessionmaker(bind=create_engine(f"sqlite:///{db_file}"))

        def fake_execute(self, strategy_config, problem, strategy, sandbox):
            other = reader()
            try:
                task = other.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
                seen.append(dict(task.progress))
            finally:
                other.close()
            integration_harness.execute_calls.append((strategy_config.name, problem.problem_id))
            return ExecutionResult(
                problem_id=problem.problem_id,
                strategy=strategy_config.name,
                generated_code="def solution(**kw):\n    return 1",
                status="success",
                total_tokens=10,
                execution_time_seconds=0.5,
                difficulty="easy",
            )

        def fake_update_state(*_args, **kwargs):
            meta = kwargs.get("meta")
            if isinstance(meta, dict):
                metas.append(dict(meta))

        monkeypatch.setattr(AlgorithmHarness, "_execute_problem", fake_execute)
        monkeypatch.setattr(run_evaluation_task, "update_state", fake_update_state)
        with patch("src.tasks.evaluation.get_db_session", return_value=db):
            run_evaluation_task(evaluation_id)

        assert [item["current_step"] for item in seen] == ["vanilla/p1", "vanilla/p2"]
        assert seen[0]["percentage"] == 0
        assert seen[1]["percentage"] == 50
        assert all(0 <= item["percentage"] <= 100 for item in seen)
        assert all("hidden problem body" not in item["current_step"] for item in seen)
        assert metas[0]["percentage"] == 0
        assert metas[0]["current_step"] == "vanilla/p1"
        db.close()

    def test_run_evaluation_task_pause_keeps_progress(
        self, integration_harness, auth_ok, monkeypatch, tmp_path
    ):
        """暂停后任务保持 paused，且最后一次进度仍在。"""
        db_file = tmp_path / "pause-progress.sqlite3"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        evaluation_id = _seed_evaluation(
            db,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
        )
        ext = sessionmaker(bind=create_engine(f"sqlite:///{db_file}"))

        def fake_update_state(*_args, **_kwargs):
            other = ext()
            try:
                row = other.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
                if row.status == "running":
                    row.status = "paused"
                    other.commit()
            finally:
                other.close()

        monkeypatch.setattr(run_evaluation_task, "update_state", fake_update_state)
        with patch("src.tasks.evaluation.get_db_session", return_value=db):
            result = run_evaluation_task(evaluation_id)

        task = db.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
        assert result["status"] == "paused"
        assert task.status == "paused"
        assert task.progress["percentage"] == 0
        assert task.progress["current_step"] == "vanilla/p1"
        assert len(integration_harness.execute_calls) == 1
        db.close()

    def test_run_evaluation_task_detects_user_pause_cross_process(
        self, integration_harness, auth_ok, monkeypatch, tmp_path
    ):
        """I-1 回归：用户经另一进程/连接写 paused，worker session 必须重新读库检出。

        业务 session 配 expire_on_commit=False：identity map 缓存的 AsyncTask 实例不会
        被后续 commit 过期，故 should_pause 的普通 ``.first()`` 命中缓存、不重新 SELECT，
        另一连接（模拟 API 进程 pause_task）写入的 "paused" 对它不可见。本用例复刻该
        session 配置，用**独立 engine/连接**在首单元完成后把 AsyncTask 改成 paused，
        断言 should_pause 仍能跨连接检出、以 paused 收尾且仅首单元真实执行。

        修复前（should_pause 无 populate_existing）：任务看不到外部 paused 写入 →
        两单元全跑 → completed，本用例失败（RED）。
        修复后（should_pause 加 populate_existing()）：强制重读 → iter2 检出 paused →
        paused，仅首单元执行（GREEN）。
        """
        db_file = tmp_path / "app.db"
        task_engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(task_engine)
        # 复刻生产业务 session：expire_on_commit=False，让 identity map 保持陈旧。
        db = sessionmaker(bind=task_engine, expire_on_commit=False)()

        evaluation_id = _seed_evaluation(
            db,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
        )
        # TaskManager 被替换后不会把任务写成 running。进度只在 running 时上报，
        # 这里直接把行标成 running，让跨连接暂停仍能挂在第一次进度上报上。
        task = db.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
        task.status = "running"
        db.commit()
        # 第二个 engine == 第二条独立连接，模拟「另一进程」的 DB 写入。
        ext_session_factory = sessionmaker(bind=create_engine(f"sqlite:///{db_file}"))

        written = {"done": False}

        def _write_pause() -> None:
            ext = ext_session_factory()
            try:
                row = ext.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).first()
                row.status = "paused"
                ext.commit()
            finally:
                ext.close()
            written["done"] = True

        calls = {"n": 0}

        def fake_update_state(*_a, **_k):
            # 单元开始前的进度上报调用 update_state。此时该单元尚未执行，写入 paused
            # 后它仍会被提交；下一轮 should_pause 必须能跨连接看到，并不再开始后续单元。
            calls["n"] += 1
            if calls["n"] == 1:
                _write_pause()

        monkeypatch.setattr(run_evaluation_task, "update_state", fake_update_state)

        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db),
        ):
            result = run_evaluation_task(evaluation_id)

        assert written["done"], "外部 paused 写入未发生，测试无效"
        ev = _reload(db, Evaluation, evaluation_id)
        assert ev.status == "paused"
        assert result["status"] == "paused"
        # 严格在首单元边界停止：第二单元从未真实执行
        assert len(integration_harness.execute_calls) == 1
        db.close()

    def test_run_evaluation_task_invalid_row_reports_invalid_not_missing(
        self, db_session, integration_harness, auth_ok
    ):
        """I-6 集成：ORM 行存在但非法（ValidationError）→ 单元失败原因含 invalid/incomplete。

        修复前该单元的 error_message 恒为 “not found in problem store”（非法与缺失不分），
        使用户误以为需重复导入而不是修脏数据。修复后缺失原因随单元真实下传。
        """
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p_exist", "p_bad"],
            strategy_names=["vanilla"],
            seed_problem_ids=["p_exist"],
        )
        # 额外 seed 一行“存在但非法”的 ORM Problem：description 短于 min_length=10
        # → _to_domain_problem 抛 ValidationError（非 row is None）。
        db_session.add(
            ORMProblem(
                id=str(uuid.uuid4()),
                problem_id="p_bad",
                title="Bad",
                description="",  # 非法：短于 domain description 的 min_length=10
                difficulty="easy",
                tags=[],
                constraints=None,
                test_cases=[{"input": {"x": 1}, "expected_output": 1}],
                source_platform=None,
                source_url=None,
            )
        )
        db_session.commit()

        with (
            patch("src.tasks.evaluation.TaskManager"),
            patch("src.tasks.evaluation.get_db_session", return_value=db_session),
        ):
            run_evaluation_task(evaluation_id)

        rows = {r.problem_id: r for r in db_session.query(EvaluationResult).all()}
        bad_row = rows["p_bad"]
        assert bad_row.status == "failed"
        assert "invalid/incomplete problem data" in (bad_row.error_message or "")
        assert "not found" not in (bad_row.error_message or "")
        # 合法且命中的题目照常成功（部分非法不阻断其余单元）
        assert rows["p_exist"].status == "success"

    def test_cancelled_evaluation_returns_without_execution(
        self, db_session, integration_harness, auth_ok
    ):
        """任务在启动前已是 cancelled 时，不解析执行、不跑单元。"""
        evaluation_id = _seed_evaluation(
            db_session,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
        )
        task = db_session.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
        task.status = "cancelled"
        db_session.commit()

        with patch("src.tasks.evaluation.get_db_session", return_value=db_session):
            result = run_evaluation_task(evaluation_id)

        evaluation = _reload(db_session, Evaluation, evaluation_id)
        assert result["status"] == "cancelled"
        assert result["completed_units"] == 0
        assert evaluation.status == "cancelled"
        assert integration_harness.execute_calls == []

    def test_cancel_during_run_stops_remaining_units(
        self, integration_harness, auth_ok, monkeypatch, tmp_path
    ):
        """运行中取消后不再派发剩余单元，收尾保持 cancelled。"""
        db_file = tmp_path / "cancel.sqlite3"
        engine = create_engine(f"sqlite:///{db_file}")
        Base.metadata.create_all(engine)
        db = sessionmaker(bind=engine, expire_on_commit=False)()
        evaluation_id = _seed_evaluation(
            db,
            problem_ids=["p1", "p2"],
            strategy_names=["vanilla"],
        )
        ext = sessionmaker(bind=create_engine(f"sqlite:///{db_file}"))

        def fake_update_state(*_args, **_kwargs):
            other = ext()
            try:
                row = other.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
                if row.status != "cancelled":
                    row.status = "cancelled"
                    other.commit()
                    TaskService(root=f"data/tasks/{evaluation_id}").request_cancel(
                        f"eval-{evaluation_id}"
                    )
            finally:
                other.close()

        monkeypatch.setattr(run_evaluation_task, "update_state", fake_update_state)
        with patch("src.tasks.evaluation.get_db_session", return_value=db):
            result = run_evaluation_task(evaluation_id)

        task = db.query(AsyncTask).filter(AsyncTask.entity_id == evaluation_id).one()
        evaluation = db.query(Evaluation).filter(Evaluation.id == evaluation_id).one()
        assert result["status"] == "cancelled"
        assert task.status == "cancelled"
        assert evaluation.status == "cancelled"
        assert len(integration_harness.execute_calls) < 2
        db.close()
