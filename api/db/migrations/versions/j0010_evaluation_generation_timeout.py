"""Persist Web evaluation generation timeouts."""

import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evaluations", sa.Column("generation_timeout_seconds", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("evaluations", "generation_timeout_seconds")
