"""Idempotency tests for the deployment seed script (issue #159)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from api.db.engine import make_session_factory
from api.db.models import Problem
from api.db.problem_store import ProblemStore
from src.models import SandboxConfig
from src.sandbox_executor import SandboxExecutor
from src.tasks.evaluation import _to_domain_problem

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


@pytest.mark.parametrize(
    "problem_id,code",
    [
        (
            "seed-two-sum",
            "def solution(nums, target):\n"
            "    for i in range(len(nums)):\n"
            "        for j in range(i + 1, len(nums)):\n"
            "            if nums[i] + nums[j] == target:\n"
            "                return [i, j]\n",
        ),
        (
            "seed-valid-parentheses",
            "def solution(s):\n"
            "    stack = []\n"
            "    pairs = {')': '(', ']': '[', '}': '{'}\n"
            "    for char in s:\n"
            "        if char in pairs:\n"
            "            if not stack or stack.pop() != pairs[char]:\n"
            "                return False\n"
            "        else:\n"
            "            stack.append(char)\n"
            "    return not stack\n",
        ),
        (
            "seed-binary-search",
            "def solution(nums, target):\n"
            "    left, right = 0, len(nums) - 1\n"
            "    while left <= right:\n"
            "        mid = (left + right) // 2\n"
            "        if nums[mid] == target:\n"
            "            return mid\n"
            "        if nums[mid] < target:\n"
            "            left = mid + 1\n"
            "        else:\n"
            "            right = mid - 1\n"
            "    return -1\n",
        ),
    ],
    ids=["two-sum", "valid-parentheses", "binary-search"],
)
def test_seed_problems_execute_after_import_and_repair(tmp_path, problem_id, code):
    """Seed data and repaired legacy rows must run through the worker's real adapter."""
    module = _load_seed_module()
    database_url = f"sqlite:///{tmp_path / 'seed.sqlite3'}"
    module.seed(database_url=database_url)
    engine = create_engine(database_url)
    try:
        store = ProblemStore(make_session_factory(engine))
        executor = SandboxExecutor(SandboxConfig(backend="host"))

        def check_execution():
            row = store.get_by_problem_id(problem_id)
            assert row is not None
            problem = _to_domain_problem(row)
            result = executor.execute(code, problem)
            assert result.all_passed, result
            assert len(result.test_results) == 2

        check_execution()
        # Simulate a database populated by the previous seed script.
        store.upsert_import(
            [
                {
                    "problem_id": problem_id,
                    "test_cases": [{"input": "legacy assignment text", "expected": "old"}],
                }
            ]
        )
        module.seed(database_url=database_url)
        assert store.count() == 3
        check_execution()
    finally:
        engine.dispose()
