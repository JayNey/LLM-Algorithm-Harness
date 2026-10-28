"""Persist experiment/A-B call spend without inventing legacy costs."""

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("experiments", "ab_tests"):
        op.add_column(
            table,
            sa.Column(
                "cost_tracking_complete", sa.Boolean(), nullable=False, server_default=sa.false()
            ),
        )
    op.create_table(
        "spend_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("task_id", sa.String(36), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column("strategy", sa.String(100), nullable=False),
        sa.Column("problem_id", sa.String(200)),
        sa.Column("difficulty", sa.String(16)),
        sa.Column("cost_usd", sa.Float()),
        sa.Column("unknown_reason", sa.String(64)),
        sa.Column("cached", sa.Boolean(), nullable=False),
        sa.Column("usage", sa.JSON()),
        sa.Column("pricing", sa.JSON()),
    )
    for column in ("user_id", "source", "task_id", "occurred_at"):
        op.create_index(f"ix_spend_records_{column}", "spend_records", [column])


def downgrade() -> None:
    op.drop_table("spend_records")
    for table in ("experiments", "ab_tests"):
        op.drop_column(table, "cost_tracking_complete")
