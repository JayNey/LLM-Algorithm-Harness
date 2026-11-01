"""Persist in-app notifications without dropping event identity on clear."""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "in_app_notifications",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("title_key", sa.String(200), nullable=False),
        sa.Column("body_key", sa.String(200), nullable=False),
        sa.Column("params", sa.JSON()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("read_at", sa.DateTime()),
        sa.Column("cleared_at", sa.DateTime()),
        sa.Column("resource_kind", sa.String(32)),
        sa.Column("resource_id", sa.String(64)),
        sa.Column("href", sa.String(300)),
        sa.UniqueConstraint("user_id", "event_key", name="uq_in_app_notifications_user_event"),
    )
    op.create_index("ix_in_app_notifications_user_id", "in_app_notifications", ["user_id"])
    op.create_index("ix_in_app_notifications_created_at", "in_app_notifications", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_in_app_notifications_created_at", table_name="in_app_notifications")
    op.drop_index("ix_in_app_notifications_user_id", table_name="in_app_notifications")
    op.drop_table("in_app_notifications")
