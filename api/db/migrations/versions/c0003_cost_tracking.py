"""cost tracking, budget and pricing tables for the API (issue #154)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("global_cap_usd", sa.Float(), nullable=True),
        sa.Column("difficulty_caps", sa.JSON(), nullable=True),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_budgets_user_id"), "budgets", ["user_id"], unique=True)

    op.create_table(
        "alert_rules",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("threshold_pct", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("target", sa.String(length=1000), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_rules_user_id"), "alert_rules", ["user_id"], unique=False)

    op.create_table(
        "alert_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=64), nullable=False),
        sa.Column("rule_id", sa.String(length=36), nullable=True),
        sa.Column("threshold_pct", sa.Integer(), nullable=False),
        sa.Column("used_usd", sa.Float(), nullable=False),
        sa.Column("cap_usd", sa.Float(), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["rule_id"], ["alert_rules.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_alert_events_user_id"), "alert_events", ["user_id"], unique=False)
    op.create_index(op.f("ix_alert_events_rule_id"), "alert_events", ["rule_id"], unique=False)

    op.create_table(
        "pricing_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("model", sa.String(length=200), nullable=False),
        sa.Column("prompt_per_1k", sa.Float(), nullable=False),
        sa.Column("completion_per_1k", sa.Float(), nullable=False),
        sa.Column("created_by", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_pricing_overrides_model"), "pricing_overrides", ["model"], unique=False
    )
    op.create_index(
        op.f("ix_pricing_overrides_created_by"), "pricing_overrides", ["created_by"], unique=False
    )


def downgrade() -> None:
    op.drop_table("pricing_overrides")
    op.drop_table("alert_events")
    op.drop_table("alert_rules")
    op.drop_index(op.f("ix_budgets_user_id"), table_name="budgets")
    op.drop_table("budgets")
