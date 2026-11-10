"""Preserve external delivery outcomes in the existing alert history."""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "alert_events",
        sa.Column("status", sa.String(16), nullable=False, server_default="succeeded"),
    )
    op.execute("UPDATE alert_events SET status = 'pending' WHERE channel = 'pending'")


def downgrade() -> None:
    op.execute("DELETE FROM alert_events WHERE status = 'failed'")
    op.drop_column("alert_events", "status")
