"""Persist immutable Web incremental plans and public counts."""

import sqlalchemy as sa
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluations",
        sa.Column("reuse_history", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("evaluations", sa.Column("reuse_plan", sa.JSON(), nullable=True))
    op.add_column(
        "evaluations", sa.Column("reused_units", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("evaluations", "reused_units")
    op.drop_column("evaluations", "reuse_plan")
    op.drop_column("evaluations", "reuse_history")
