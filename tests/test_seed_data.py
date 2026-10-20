"""Idempotency tests for the deployment seed script (issue #159)."""

import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.db.models import Problem

SEED_MODULE = Path(__file__).resolve().parents[1] / "scripts" / "seed_data.py"


def _load_seed_module():
    spec = importlib.util.spec_from_file_location("seed_data", SEED_MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_seed_is_idempotent(tmp_path):
    """Running the seed twice keeps exactly one row per seed problem."""
    module = _load_seed_module()
    database_url = f"sqlite:///{tmp_path / 'seed.sqlite3'}"

    first = module.seed(database_url=database_url)
    second = module.seed(database_url=database_url)

    assert first == len(module.SEED_PROBLEMS)
    assert second == first

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(Problem)).all()
            problem_ids = {row.problem_id for row in rows}
            assert len(rows) == len(module.SEED_PROBLEMS)
            assert problem_ids == {p["problem_id"] for p in module.SEED_PROBLEMS}
    finally:
        engine.dispose()


def test_seed_survives_partial_update(tmp_path):
    """A changed field is updated in place rather than duplicated."""
    module = _load_seed_module()
    database_url = f"sqlite:///{tmp_path / 'seed.sqlite3'}"

    module.seed(database_url=database_url)
    mutated = [dict(module.SEED_PROBLEMS[0], title="Two Sum (renamed)")]
    module.seed(database_url=database_url, problems=mutated)

    engine = create_engine(database_url)
    try:
        with Session(engine) as session:
            rows = session.scalars(select(Problem)).all()
            by_seed_id = {row.problem_id: row for row in rows}
            assert len(rows) == len(module.SEED_PROBLEMS)
            assert by_seed_id["seed-two-sum"].title == "Two Sum (renamed)"
    finally:
        engine.dispose()
