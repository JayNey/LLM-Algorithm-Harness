"""Associate evaluations with immutable personal dataset versions."""

import sqlalchemy as sa
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evaluations", sa.Column("dataset_version_id", sa.String(64), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluations", "dataset_version_id")
