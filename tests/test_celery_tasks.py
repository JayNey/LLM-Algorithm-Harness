"""Celery 任务单元测试

测试 run_evaluation_task 的核心功能，包括任务生命周期管理、进度报告和错误处理。
"""

import uuid
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from api.db.models import AsyncTask, Base, Evaluation
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
                with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
                    mock_get_db.return_value = db_session

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

                with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
                    mock_get_db.return_value = db_session

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

                with patch("src.tasks.evaluation.get_db_session") as mock_get_db:
                    mock_get_db.return_value = db_session

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
        """题目缺失记入 missing_problems，不 fail-fast；存在的题目进入 problem_map。"""
        from src.tasks.evaluation import _resolve_execution_context

        ev = make_evaluation(model="m", problem_ids=["p1", "missing"])
        sentinel_llm = object()
        sentinel_problem = object()

        class _FakeStore:
            def __init__(self, _session_factory):
                pass

            def get_by_problem_id(self, problem_id):
                return sentinel_problem if problem_id == "p1" else None

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
        assert ctx.problem_map["p1"] is sentinel_problem
