import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from api.db.models import Base, Evaluation, EvaluationResult, Problem
from api.services.evaluation_results_service import (
    EvaluationResultsService,
    _json_array_contains,
)


def _seed(tmp_path):
    url = f"sqlite:///{tmp_path}/biz.sqlite3"
    engine = create_engine(url)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(
            Problem(
                id="p1",
                problem_id="two-sum",
                title="Two Sum",
                difficulty="easy",
                tags=["array"],
            )
        )
        owned = Evaluation(
            id="eval-own",
            user_id="owner",
            run_id="run-own",
            status="completed",
            strategy_names=["vanilla", "retry"],
            problem_ids=["two-sum"],
            model="gpt-test",
            created_at=datetime(2026, 10, 1, 0, 0, 0),
            completed_at=datetime(2026, 10, 1, 1, 0, 0),
        )
        other = Evaluation(
            id="eval-other",
            user_id="other",
            run_id="run-other",
            status="completed",
            strategy_names=["vanilla"],
            problem_ids=["two-sum"],
            model="gpt-test",
        )
        db.add_all([owned, other])
        db.add_all(
            [
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "success": True,
                        "total_tokens": 10,
                        "execution_time_seconds": 1.0,
                        "cost_usd": 0.2,
                        "cost_unknown": False,
                        "difficulty": "easy",
                        "iterations": 1,
                    },
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-own",
                    problem_id="two-sum",
                    strategy_name="retry",
                    status="failed",
                    metrics={
                        "success": False,
                        "total_tokens": 30,
                        "execution_time_seconds": 3.0,
                        "cost_usd": 9.0,
                        "cost_unknown": True,
                        "difficulty": "easy",
                    },
                    error_message="boom",
                ),
                EvaluationResult(
                    id=str(uuid.uuid4()),
                    evaluation_id="eval-other",
                    problem_id="two-sum",
                    strategy_name="vanilla",
                    status="success",
                    metrics={
                        "iterations": 1,
                        "total_tokens": 1,
                        "cost_usd": 1,
                        "cost_unknown": False,
                    },
                ),
            ]
        )
        db.commit()
    return url


def test_detail_scopes_to_owner_and_keeps_full_strategy_summary(tmp_path):
    service = EvaluationResultsService(_seed(tmp_path))
    with pytest.raises(ValueError, match="not found"):
        service.detail("owner", "eval-other")
    data = service.detail("owner", "run-own", limit=1, offset=0)
    vanilla = next(item for item in data["strategies"] if item["name"] == "vanilla")
    assert vanilla["success_rate"] == 1.0
    assert vanilla["solved_problems"] == 1
    assert vanilla["total_problems"] == 1
    assert vanilla["estimated_cost_usd"] == 0.2
    assert vanilla["avg_execution_time"] == 1.0
    retry = next(item for item in data["strategies"] if item["name"] == "retry")
    assert retry["estimated_cost_usd"] == 0.0
    assert retry["unknown_cost_count"] == 1
    assert len(data["strategies"]) == 2
    assert data["problems"]["total"] == 2
    assert len(data["problems"]["items"]) == 1
    history, total = service.problem_history("owner", "two-sum", status=None, limit=20, offset=0)
    assert total == 2
    assert all(item["run_id"] == "run-own" for item in history)
    runs, run_total = service.list_runs(
        "owner",
        strategy=None,
        difficulty=None,
        tag="array",
        status="completed",
        limit=20,
        offset=0,
        sort="completed_at",
        order="desc",
    )
    assert run_total == 1
    assert runs[0]["run_id"] == "run-own"


def test_postgresql_tag_filter_binds_tag_without_bare_json_array_elements():
    """PostgreSQL tag SQL is a bound @> or LATERAL predicate.

    Breaks if the compiler calls json_array_elements on an outer row without
    LATERAL, or writes the tag into the SQL text.
    """
    tag = "a\\b"
    statement = select(Problem.id).where(_json_array_contains(Problem.tags, tag))
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = " ".join(str(compiled).split())
    assert "LATERAL" in sql or "@>" in sql
    assert tag in compiled.params.values()
    assert tag not in sql
    assert "json_array_elements" not in sql or "LATERAL" in sql


def _compiled_list_order(tmp_path, order: str) -> str:
    service = EvaluationResultsService(_seed(tmp_path))
    captured: list = []
    factory = service._session_factory

    def capturing_factory():
        session = factory()
        original_scalars = session.scalars

        def scalars(statement, *args, **kwargs):
            captured.append(statement)
            return original_scalars(statement, *args, **kwargs)

        session.scalars = scalars
        return session

    service._session_factory = capturing_factory
    service.list_runs(
        "owner",
        strategy=None,
        difficulty=None,
        tag=None,
        status=None,
        limit=1,
        offset=0,
        sort="completed_at",
        order=order,
    )
    return " ".join(str(captured[-1].compile(dialect=postgresql.dialect())).split())


def test_list_runs_descending_completed_at_is_nulls_last(tmp_path):
    """Descending completed_at puts nulls last on PostgreSQL.

    Breaks if list_runs uses column.desc() alone: PostgreSQL then sorts null
    completed_at ahead of real timestamps.
    """
    sql = _compiled_list_order(tmp_path, "desc").upper()
    assert "NULLS LAST" in sql


def test_list_runs_ascending_completed_at_is_nulls_first(tmp_path):
    """Ascending completed_at puts nulls first on PostgreSQL.

    Breaks if list_runs uses column.asc() alone: PostgreSQL then sorts null
    completed_at after real timestamps.
    """
    sql = _compiled_list_order(tmp_path, "asc").upper()
    assert "NULLS FIRST" in sql
