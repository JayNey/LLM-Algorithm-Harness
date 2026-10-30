"""评估操作能力与同 ID 启动的数据库契约。"""

import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi import HTTPException
from sqlalchemy import event, select

from api.db.models import AsyncTask, Evaluation
from api.models import EvaluationCreateRequest, EvaluationUpdateRequest
from api.routes.evaluations import call
from api.services.evaluation_service import EvaluationService
from src.task_manager import TaskManager, celery_app

OWNER = "workflow-owner"


@pytest.fixture
def service(tmp_path):
    instance = EvaluationService(f"sqlite:///{tmp_path / 'workflow.sqlite3'}")
    yield instance
    instance.close()


@pytest.fixture
def publisher(monkeypatch):
    publish = Mock(return_value=SimpleNamespace(id="broker-result"))
    monkeypatch.setattr(celery_app, "send_task", publish)
    monkeypatch.setattr(celery_app, "AsyncResult", lambda _: SimpleNamespace(state="PENDING"))
    monkeypatch.setattr(celery_app.control, "revoke", Mock())
    return publish


def create(service):
    return service.create_evaluation(
        EvaluationCreateRequest(
            api_key_id="test-credential",
            problem_ids=["p1"],
            strategy_names=["vanilla"],
            model="test-model",
        ),
        OWNER,
    )


def set_state(service, evaluation_id, status, linked_status):
    with service._session() as session, session.begin():
        evaluation = session.get(Evaluation, evaluation_id)
        evaluation.status = status
        if linked_status is not None:
            task = AsyncTask(
                id=f"linked-{evaluation_id}",
                celery_task_id=f"celery-{evaluation_id}",
                task_type="evaluation",
                entity_id=evaluation_id,
                user_id=OWNER,
                status=linked_status,
            )
            session.add(task)
            session.flush()
            evaluation.async_task_id = task.id


def capabilities(response):
    data = response.model_dump()
    assert data.get("execution_progress") == {
        "completed_units": 0,
        "total_units": 1,
        "percentage": 0.0,
    }
    return data.get("can_start"), data.get("can_cancel")


# 缺失任务感知、终态优先或 legacy running 分支都会破坏此公开响应矩阵。
@pytest.mark.parametrize(
    "status,linked_status,want",
    [
        ("pending", None, (True, False)),
        ("pending", "pending", (False, True)),
        ("pending", "running", (False, True)),
        ("pending", "paused", (False, True)),
        ("pending", "failed", (True, False)),
        ("pending", "completed", (True, False)),
        ("pending", "cancelled", (True, False)),
        ("running", None, (False, True)),
        ("running", "running", (False, True)),
        ("paused", "paused", (False, True)),
        ("completed", "pending", (False, False)),
        ("failed", "running", (False, False)),
        ("cancelled", "paused", (False, False)),
        ("completed", "completed", (False, False)),
        ("failed", "failed", (False, False)),
        ("cancelled", "cancelled", (False, False)),
    ],
)
def test_capabilities_match_on_details_list_and_async_helper(
    service, monkeypatch, status, linked_status, want
):
    evaluation_id = create(service).evaluation_id
    set_state(service, evaluation_id, status, linked_status)

    def no_broker_read(*_args, **_kwargs):
        pytest.fail("响应投影不能同步 Celery 状态")

    monkeypatch.setattr(TaskManager, "get_task", no_broker_read)
    assert capabilities(service.get_evaluation(evaluation_id, OWNER)) == want
    assert capabilities(service.get_evaluation_async(evaluation_id, OWNER)) == want
    if status == "pending":
        assert (
            capabilities(
                service.update_evaluation(
                    evaluation_id, EvaluationUpdateRequest(budget_cap_usd=2), OWNER
                )
            )
            == want
        )
    items, total = service.list_evaluations(OWNER)
    assert total == 1
    assert capabilities(items[0]) == want


def test_create_update_start_and_cancel_expose_capabilities(service, publisher):
    fresh = create(service)
    assert capabilities(fresh) == (True, False)
    updated = service.update_evaluation(
        fresh.evaluation_id, EvaluationUpdateRequest(budget_cap_usd=2), OWNER
    )
    assert capabilities(updated) == (True, False)
    queued = service.start_evaluation(fresh.evaluation_id, OWNER)
    assert capabilities(queued) == (False, True)
    cancelled = service.cancel_evaluation(fresh.evaluation_id, OWNER)
    assert capabilities(cancelled) == (False, False)


def test_async_create_pause_and_resume_expose_capabilities(service, publisher):
    queued = service.create_evaluation_async(
        EvaluationCreateRequest(
            api_key_id="test-credential",
            problem_ids=["p1"],
            strategy_names=["vanilla"],
            model="test-model",
        ),
        OWNER,
    )
    assert capabilities(queued) == (False, True)
    with service._session() as session, session.begin():
        evaluation = session.get(Evaluation, queued.evaluation_id)
        session.get(AsyncTask, evaluation.async_task_id).status = "running"
    paused = service.pause_evaluation(queued.evaluation_id, OWNER)
    assert capabilities(paused) == (False, True)
    resumed = service.resume_evaluation(queued.evaluation_id, OWNER)
    assert capabilities(resumed) == (False, True)


def test_list_loads_linked_tasks_in_one_query(service, monkeypatch):
    for status in ("pending", "running", "paused"):
        fresh = create(service)
        set_state(service, fresh.evaluation_id, "pending", status)
    statements = []

    def capture(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement)

    event.listen(service.engine, "before_cursor_execute", capture)
    try:
        items, total = service.list_evaluations(OWNER)
    finally:
        event.remove(service.engine, "before_cursor_execute", capture)
    assert total == 3
    assert [capabilities(item) for item in items] == [(False, True)] * 3
    assert sum("FROM async_tasks" in statement for statement in statements) == 1


def test_publish_failure_is_retryable_without_recreating_evaluation(service, publisher):
    evaluation_id = create(service).evaluation_id
    publisher.side_effect = ConnectionError("broker unavailable")
    with pytest.raises(ConnectionError, match="broker unavailable"):
        service.start_evaluation(evaluation_id, OWNER)
    assert capabilities(service.get_evaluation(evaluation_id, OWNER)) == (True, False)
    with service._session() as session:
        previous_id = session.get(Evaluation, evaluation_id).async_task_id
        assert session.get(AsyncTask, previous_id).status == "failed"
    publisher.side_effect = None
    assert capabilities(service.start_evaluation(evaluation_id, OWNER)) == (False, True)
    with service._session() as session:
        assert session.get(Evaluation, evaluation_id).async_task_id != previous_id
        assert len(session.scalars(select(Evaluation)).all()) == 1


# 在入队前等待意味着两个调用都已读取旧关联，移除 CAS 会产生两个任务和两次发布。
@pytest.mark.parametrize("linked_status", [None, "failed"])
def test_concurrent_start_claims_same_id_once(service, publisher, monkeypatch, linked_status):
    evaluation_id = create(service).evaluation_id
    set_state(service, evaluation_id, "pending", linked_status)
    rendezvous = threading.Barrier(2, timeout=5)
    original_enqueue = TaskManager.enqueue_task
    sessions = []

    def overlap(manager, *args, **kwargs):
        sessions.append(manager.db)
        rendezvous.wait()
        return original_enqueue(manager, *args, **kwargs)

    monkeypatch.setattr(TaskManager, "enqueue_task", overlap)

    def start():
        try:
            return service.start_evaluation(evaluation_id, OWNER)
        except ValueError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(start) for _ in range(2)]
        outcomes = [future.result(timeout=15) for future in futures]
    assert len(sessions) == 2 and sessions[0] is not sessions[1]
    assert sum(not isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert sum(isinstance(outcome, ValueError) for outcome in outcomes) == 1
    assert publisher.call_count == 1
    with service._session() as session:
        candidates = session.scalars(select(AsyncTask).where(AsyncTask.status == "pending")).all()
        assert len(candidates) == 1
        assert session.get(Evaluation, evaluation_id).async_task_id == candidates[0].id
        all_tasks = session.scalars(select(AsyncTask)).all()
        assert len(all_tasks) == (1 if linked_status is None else 2)


# 首次读取后终态/归属变化必须令事务内占位失败，候选行不得被提交或发布。
@pytest.mark.parametrize(
    "changed_field,changed_value",
    [("status", "cancelled"), ("status", "completed"), ("user_id", "new-owner")],
)
def test_start_rejects_state_or_owner_changed_before_link(
    service, publisher, monkeypatch, changed_field, changed_value
):
    evaluation_id = create(service).evaluation_id
    original_enqueue = TaskManager.enqueue_task

    def intervene(manager, *args, **kwargs):
        with service._session() as other, other.begin():
            setattr(other.get(Evaluation, evaluation_id), changed_field, changed_value)
        return original_enqueue(manager, *args, **kwargs)

    monkeypatch.setattr(TaskManager, "enqueue_task", intervene)
    with pytest.raises(HTTPException) as error:
        call(lambda: service.start_evaluation(evaluation_id, OWNER))
    assert error.value.status_code == 400
    assert publisher.call_count == 0
    with service._session() as session:
        assert session.scalars(select(AsyncTask)).all() == []
        evaluation = session.get(Evaluation, evaluation_id)
        assert getattr(evaluation, changed_field) == changed_value
        assert evaluation.async_task_id is None


def test_start_preserves_initial_owner_and_status_errors(service, publisher):
    evaluation_id = create(service).evaluation_id
    with pytest.raises(HTTPException) as error:
        call(lambda: service.start_evaluation(evaluation_id, "other-owner"))
    assert error.value.status_code == 404
    set_state(service, evaluation_id, "completed", None)
    with pytest.raises(HTTPException) as error:
        call(lambda: service.start_evaluation(evaluation_id, OWNER))
    assert error.value.status_code == 400
    assert publisher.call_count == 0


# 遗漏失败单元、未钳制计数或根据终态强填 100% 都会破坏此公开响应契约。
@pytest.mark.parametrize(
    "status", ["pending", "running", "paused", "completed", "failed", "cancelled"]
)
@pytest.mark.parametrize(
    "problem_count,strategies,completed,failed,want",
    [
        (2, ["vanilla", "cot"], 1, 1, {"completed_units": 2, "total_units": 4, "percentage": 50.0}),
        (0, ["vanilla"], 0, 1, {"completed_units": 0, "total_units": 0, "percentage": 0.0}),
        (2, [], 1, 1, {"completed_units": 0, "total_units": 0, "percentage": 0.0}),
        (
            2,
            ["vanilla", "cot"],
            1,
            9,
            {"completed_units": 4, "total_units": 4, "percentage": 100.0},
        ),
        (2, ["vanilla", "cot"], 1, -5, {"completed_units": 0, "total_units": 4, "percentage": 0.0}),
    ],
)
def test_execution_progress_counts_finished_units_in_every_status(
    service, status, problem_count, strategies, completed, failed, want
):
    evaluation_id = create(service).evaluation_id
    with service._session() as session, session.begin():
        row = session.get(Evaluation, evaluation_id)
        row.status = status
        row.problem_count = problem_count
        row.strategy_names = strategies
        row.completed_count = completed
        row.failed_count = failed
    detail = service.get_evaluation(evaluation_id, OWNER).model_dump()
    assert detail.get("execution_progress") == want
    assert (
        service.get_evaluation_async(evaluation_id, OWNER).model_dump()["execution_progress"]
        == want
    )
    items, _ = service.list_evaluations(OWNER)
    assert items[0].model_dump()["execution_progress"] == want
    if problem_count == 2 and strategies and failed == 1:
        assert detail["progress"]["percentage"] == 25.0


def test_execution_progress_preserves_async_task_progress(service):
    evaluation_id = create(service).evaluation_id
    set_state(service, evaluation_id, "running", "running")
    with service._session() as session, session.begin():
        row = session.get(Evaluation, evaluation_id)
        row.problem_count = 2
        row.strategy_names = ["vanilla", "cot"]
        row.completed_count = 1
        row.failed_count = 1
        session.get(AsyncTask, row.async_task_id).progress = {
            "current": 7,
            "total": 10,
            "percentage": 70.0,
            "message": "worker 原值",
        }
    body = service.get_evaluation_async(evaluation_id, OWNER).model_dump()
    assert body.get("execution_progress") == {
        "completed_units": 2,
        "total_units": 4,
        "percentage": 50.0,
    }
    assert body["progress"] == {
        "current": 7,
        "total": 10,
        "percentage": 70.0,
        "message": "worker 原值",
        "completed": None,
    }


@pytest.mark.parametrize(
    "status,linked,stopped,want",
    [
        ("pending", None, False, (False, False, True, True)),
        ("running", "running", False, (True, False, False, False)),
        ("paused", "paused", False, (False, True, False, False)),
        ("paused", "paused", True, (False, True, False, False)),
        ("completed", "running", True, (False, False, False, True)),
        ("failed", "failed", True, (False, False, False, False)),
        ("cancelled", "cancelled", True, (False, False, False, True)),
    ],
)
def test_management_capabilities(service, status, linked, stopped, want):
    eid = create(service).evaluation_id
    set_state(service, eid, status, linked)
    if linked:
        with service._session() as session, session.begin():
            session.get(AsyncTask, f"linked-{eid}").progress = {"stop_confirmed": stopped}
    for response in (service.get_evaluation(eid, OWNER), service.list_evaluations(OWNER)[0][0]):
        data = response.model_dump()
        assert (
            tuple(data.get(k) for k in ("can_pause", "can_resume", "can_update", "can_delete"))
            == want
        )
        assert data["async_task_id"] == (f"linked-{eid}" if linked else None)


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", "another-owner"),
        ("entity_id", "another-evaluation"),
        ("task_type", "experiment"),
    ],
)
def test_management_rejects_unrelated_task_link(service, field, value):
    eid = create(service).evaluation_id
    set_state(service, eid, "running", "running")
    with service._session() as session, session.begin():
        setattr(session.get(AsyncTask, f"linked-{eid}"), field, value)
    data = service.get_evaluation(eid, OWNER).model_dump()
    assert data.get("async_task_id") is None
    assert data.get("can_pause") is False
