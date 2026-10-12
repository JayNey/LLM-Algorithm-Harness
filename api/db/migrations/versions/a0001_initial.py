"""initial business schema

Revision ID: 0001
Revises:
Create Date: 2026-10-12

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "problems",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("problem_id", sa.String(length=200), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.String(length=16), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("constraints", sa.Text(), nullable=True),
        sa.Column("test_cases", sa.JSON(), nullable=True),
        sa.Column("source_platform", sa.String(length=100), nullable=True),
        sa.Column("source_url", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("problem_id"),
    )
    op.create_index(op.f("ix_problems_problem_id"), "problems", ["problem_id"], unique=True)

    op.create_table(
        "evaluations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("run_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("strategy_names", sa.JSON(), nullable=False),
        sa.Column("problem_ids", sa.JSON(), nullable=False),
        sa.Column("problem_count", sa.Integer(), nullable=False),
        sa.Column("api_key_id", sa.String(length=64), nullable=True),
        sa.Column("budget_cap_usd", sa.Float(), nullable=True),
        sa.Column("spent_usd", sa.Float(), nullable=False),
        sa.Column("completed_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_evaluations_user_id"), "evaluations", ["user_id"], unique=False)
    op.create_index(op.f("ix_evaluations_status"), "evaluations", ["status"], unique=False)

    op.create_table(
        "evaluation_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("evaluation_id", sa.String(length=36), nullable=False),
        sa.Column("problem_id", sa.String(length=200), nullable=False),
        sa.Column("strategy_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["evaluation_id"], ["evaluations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_evaluation_results_evaluation_id"),
        "evaluation_results",
        ["evaluation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_results_problem_id"),
        "evaluation_results",
        ["problem_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_evaluation_results_strategy_name"),
        "evaluation_results",
        ["strategy_name"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("evaluation_results")
    op.drop_index(op.f("ix_evaluations_status"), table_name="evaluations")
    op.drop_index(op.f("ix_evaluations_user_id"), table_name="evaluations")
    op.drop_table("evaluations")
    op.drop_index(op.f("ix_problems_problem_id"), table_name="problems")
    op.drop_table("problems")
