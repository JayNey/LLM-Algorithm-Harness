"""Persist truthful evaluation payloads and independently recoverable publications."""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluation_results", sa.Column("execution_payload", sa.JSON(), nullable=True))
    op.create_table(
        "evaluation_artifact_publications",
        sa.Column(
            "evaluation_id",
            sa.String(36),
            sa.ForeignKey("evaluations.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
        sa.Column("source_task_id", sa.String(36)),
        sa.Column("source_generation", sa.String(255)),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("published_revision", sa.Integer()),
        sa.Column("error_code", sa.String(64)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_evaluation_artifact_publications_user_id",
        "evaluation_artifact_publications",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_table("evaluation_artifact_publications")
    op.drop_column("evaluation_results", "execution_payload")
