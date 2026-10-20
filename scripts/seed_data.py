#!/usr/bin/env python3
"""Seed minimal example problems into the business database (issue #159).

Usage:
    python3 scripts/seed_data.py [--database-url URL]

The script runs pending migrations first and then upserts a small set of
example problems, so it is safe to run repeatedly: re-importing the same
records updates them in place instead of creating duplicates.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as a script straight from a checkout.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

SEED_PROBLEMS: list[dict] = [
    {
        "problem_id": "seed-two-sum",
        "title": "Two Sum",
        "description": (
            "Given an array of integers nums and an integer target, return "
            "indices of the two numbers such that they add up to target."
        ),
        "difficulty": "easy",
        "tags": ["array", "hash-table"],
        "constraints": "2 <= len(nums) <= 10^4; exactly one valid answer exists.",
        "test_cases": [
            {"input": "nums = [2,7,11,15], target = 9", "expected": "[0,1]"},
            {"input": "nums = [3,2,4], target = 6", "expected": "[1,2]"},
        ],
        "source_platform": "seed",
        "source_url": None,
    },
    {
        "problem_id": "seed-valid-parentheses",
        "title": "Valid Parentheses",
        "description": (
            "Given a string s containing just the characters '(', ')', '{', '}', "
            "'[' and ']', determine if the input string is valid."
        ),
        "difficulty": "easy",
        "tags": ["string", "stack"],
        "constraints": "1 <= len(s) <= 10^4; s consists of parentheses only.",
        "test_cases": [
            {"input": 's = "()"', "expected": "true"},
            {"input": 's = "(]"', "expected": "false"},
        ],
        "source_platform": "seed",
        "source_url": None,
    },
    {
        "problem_id": "seed-binary-search",
        "title": "Binary Search",
        "description": (
            "Given an array of integers nums which is sorted in ascending order, "
            "and an integer target, write a function to search target in nums. "
            "If target exists, return its index; otherwise return -1."
        ),
        "difficulty": "medium",
        "tags": ["array", "binary-search"],
        "constraints": "1 <= len(nums) <= 10^4; all values are unique.",
        "test_cases": [
            {"input": "nums = [-1,0,3,5,9,12], target = 9", "expected": "4"},
            {"input": "nums = [-1,0,3,5,9,12], target = 2", "expected": "-1"},
        ],
        "source_platform": "seed",
        "source_url": None,
    },
]


def seed(database_url: str | None = None, problems: list[dict] | None = None) -> int:
    """Run migrations and upsert the seed problems; return the record count."""
    from api.db.engine import business_database_url, make_engine, make_session_factory
    from api.db.migrate import run_migrations
    from api.db.problem_store import ProblemStore

    engine = make_engine(database_url or business_database_url())
    try:
        run_migrations(engine)
        store = ProblemStore(make_session_factory(engine))
        return store.upsert_import(problems if problems is not None else SEED_PROBLEMS)
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed example problems (idempotent).")
    parser.add_argument(
        "--database-url",
        default=None,
        help="Business database URL; defaults to DATABASE_URL or the local SQLite file.",
    )
    args = parser.parse_args()

    count = seed(database_url=args.database_url)
    print(f"seeded {count} example problems")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
