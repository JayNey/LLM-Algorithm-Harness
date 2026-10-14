"""add nullable model column to evaluations

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13

evaluation-real-executor Task 1：为真实执行体解析 LLM 凭证提供 model 字段。
DB 层保持可空以兼容历史行；请求层的必填约束由 §5.2 单独引入。

链在 0003 (cost-tracking) 之后，保持迁移图单一线性 head。
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLite 原生支持「可空且无 server_default」的 add_column；
    # 若目标方言拒绝，再退回 batch_alter_table 模式。
    op.add_column("evaluations", sa.Column("model", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("evaluations", "model")
