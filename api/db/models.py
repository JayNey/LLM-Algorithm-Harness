"""ORM models for the business database (issue #151).

Tables mirror the issue draft: problems, evaluations and results. Users are
not modelled here — they live in the authentication store (issue #152), so
``evaluations.user_id`` references that identifier as an opaque string
without a cross-database foreign key.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp; stored consistently across SQLite and PostgreSQL."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    """Declarative base for all business tables."""


class Problem(Base):
    """An evaluation problem imported from an external dataset."""

    __tablename__ = "problems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    problem_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str] = mapped_column(Text, default="")
    difficulty: Mapped[str | None] = mapped_column(String(16))
    tags: Mapped[list | None] = mapped_column(JSON)
    constraints: Mapped[str | None] = mapped_column(Text)
    test_cases: Mapped[dict | list | None] = mapped_column(JSON)
    source_platform: Mapped[str | None] = mapped_column(String(100))
    source_url: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Evaluation(Base):
    """One evaluation run requested through the API."""

    __tablename__ = "evaluations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    run_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    strategy_names: Mapped[list] = mapped_column(JSON, default=list)
    problem_ids: Mapped[list] = mapped_column(JSON, default=list)
    problem_count: Mapped[int] = mapped_column(Integer, default=0)
    api_key_id: Mapped[str | None] = mapped_column(String(64))
    budget_cap_usd: Mapped[float | None] = mapped_column(Float)
    spent_usd: Mapped[float] = mapped_column(Float, default=0.0)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class EvaluationResult(Base):
    """Per-problem, per-strategy outcome of one evaluation run."""

    __tablename__ = "evaluation_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    problem_id: Mapped[str] = mapped_column(String(200), index=True)
    strategy_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    metrics: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Experiment(Base):
    """One API-created fixed-budget experiment (issue #156)."""

    __tablename__ = "experiments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    api_key_id: Mapped[str | None] = mapped_column(String(64))
    output_dir: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class BenchmarkSuite(Base):
    """A persisted benchmark suite for learning curve tracking."""

    __tablename__ = "benchmark_suites"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    version: Mapped[str] = mapped_column(String(32), default="1.0")
    description: Mapped[str | None] = mapped_column(Text)
    frozen: Mapped[bool] = mapped_column(Boolean, default=False)
    problems: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BenchmarkRun(Base):
    """One benchmark execution against a suite; rows feed learning curves."""

    __tablename__ = "benchmark_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("benchmark_suites.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    model: Mapped[str] = mapped_column(String(200), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    accuracy: Mapped[float | None] = mapped_column(Float)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    results: Mapped[dict | None] = mapped_column(JSON)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class ABTest(Base):
    """One API-created A/B prompt test (issue #156)."""

    __tablename__ = "ab_tests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    api_key_id: Mapped[str | None] = mapped_column(String(64))
    output_dir: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
