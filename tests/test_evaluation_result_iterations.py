import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from api.db.models import Base, Evaluation, EvaluationResult
from src.task_service import TaskUnit
from src.tasks.evaluation import _record_unit_result


def test_record_unit_result_stores_iteration_count_only():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        evaluation = Evaluation(
            id=str(uuid.uuid4()),
            user_id="owner",
            run_id="run-1",
            status="running",
            strategy_names=["vanilla"],
            problem_ids=["two-sum"],
        )
        db.add(evaluation)
        db.flush()
        _record_unit_result(
            db,
            evaluation,
            TaskUnit(
                unit_id="two-sum:vanilla",
                problem_id="two-sum",
                strategy="vanilla",
                status="completed",
                result={
                    "status": "success",
                    "iterations": [{"code": "secret"}, {"code": "still-secret"}],
                    "generated_code": "print(1)",
                    "total_tokens": 10,
                    "execution_time_seconds": 1.5,
                    "metadata": {"cost_usd": 0.1, "cost_unknown": False},
                },
            ),
        )
        db.commit()
        row = db.query(EvaluationResult).one()
        assert row.metrics["iterations"] == 2
        assert "generated_code" not in row.metrics
        assert "secret" not in str(row.metrics)
