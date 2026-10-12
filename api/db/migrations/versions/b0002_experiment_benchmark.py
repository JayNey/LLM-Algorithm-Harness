"""second wave of business tables for experiment and benchmark APIs

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-12

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_COLUMNS = [
    sa.Column("created_at", sa.DateTime(), nullable=False),
    sa.Column("updated_at", sa.DateTime(), nullable=False),
    sa.Column("started_at", sa.DateTime(), nullable=True),
    sa.Column("completed_at", sa.DateTime(), nullable=True),
]


def upgrade() -> None:
    op.create_table(
        "experiments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.Column("output_dir", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_JOB_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_experiments_user_id"), "experiments", ["user_id"], unique=False)
    op.create_index(op.f("ix_experiments_status"), "experiments", ["status"], unique=False)

    op.create_table(
        "benchmark_suites",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("frozen", sa.Boolean(), nullable=False),
        sa.Column("problems", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        op.f("ix_benchmark_suites_user_id"), "benchmark_suites", ["user_id"], unique=False
    )
    op.create_index(op.f("ix_benchmark_suites_name"), "benchmark_suites", ["name"], unique=True)

    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("suite_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_JOB_COLUMNS,
        sa.ForeignKeyConstraint(["suite_id"], ["benchmark_suites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_benchmark_runs_suite_id"), "benchmark_runs", ["suite_id"], unique=False
    )
    op.create_index(op.f("ix_benchmark_runs_user_id"), "benchmark_runs", ["user_id"], unique=False)
    op.create_index(op.f("ix_benchmark_runs_status"), "benchmark_runs", ["status"], unique=False)

    op.create_table(
        "ab_tests",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.Column("output_dir", sa.String(length=500), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        *_JOB_COLUMNS,
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ab_tests_user_id"), "ab_tests", ["user_id"], unique=False)
    op.create_index(op.f("ix_ab_tests_status"), "ab_tests", ["status"], unique=False)


def downgrade() -> None:
    op.drop_table("ab_tests")
    op.drop_table("benchmark_runs")
    op.drop_index(op.f("ix_benchmark_suites_name"), table_name="benchmark_suites")
    op.drop_index(op.f("ix_benchmark_suites_user_id"), table_name="benchmark_suites")
    op.drop_table("benchmark_suites")
    op.drop_table("experiments")
