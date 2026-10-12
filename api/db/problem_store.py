"""Idempotent problem repository over the ``problems`` table."""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from api.db.models import Problem

_DATASET_FIELDS = (
    "title",
    "description",
    "difficulty",
    "tags",
    "constraints",
    "test_cases",
    "source_platform",
    "source_url",
)


class ProblemStore:
    """CRUD and dataset import for problems.

    Kept separate from the evaluation service because problem data arrives
    from external importers (issue #135 and friends) and changes on a
    different cadence than evaluation runs.
    """

    def __init__(self, session_factory: sessionmaker[Session]):
        self._session_factory = session_factory

    def upsert_import(self, problems: Iterable[Mapping]) -> int:
        """Upsert dataset records keyed by ``problem_id``; return row count.

        Re-importing the same dataset updates fields in place instead of
        producing duplicate rows, so importers can stay repeatable.
        """
        records = list(problems)
        with self._session_factory() as session, session.begin():
            for record in records:
                problem_id = record.get("problem_id")
                if not isinstance(problem_id, str) or not problem_id:
                    raise ValueError("dataset record is missing a string problem_id")
                problem = session.scalar(select(Problem).where(Problem.problem_id == problem_id))
                if problem is None:
                    problem = Problem(
                        id=str(uuid.uuid4()),
                        problem_id=problem_id,
                        title=str(record.get("title") or problem_id),
                    )
                    session.add(problem)
                for field in _DATASET_FIELDS:
                    if field in record:
                        setattr(problem, field, record[field])
        return len(records)

    def import_json_file(self, path: str | Path) -> int:
        """Import a dataset JSON file (a list of problem records)."""
        import json

        with open(path, encoding="utf-8") as handle:
            records = json.load(handle)
        if not isinstance(records, list):
            raise ValueError(f"dataset file {path} must contain a JSON list")
        return self.upsert_import(records)

    def get_by_problem_id(self, problem_id: str) -> Problem | None:
        with self._session_factory() as session:
            return session.scalar(select(Problem).where(Problem.problem_id == problem_id))

    def list_problems(self, limit: int = 100, offset: int = 0) -> list[Problem]:
        with self._session_factory() as session:
            return list(
                session.scalars(
                    select(Problem).order_by(Problem.problem_id).limit(limit).offset(offset)
                )
            )

    def count(self) -> int:
        with self._session_factory() as session:
            return int(session.scalar(select(func.count()).select_from(Problem)) or 0)
