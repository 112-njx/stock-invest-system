"""V0.2 第二波：memory_chunks.importance（记忆重要性评分，阶段六 6.2）。

- importance：记忆重要性 1-10，用于检索加权排序（相似度×0.7 + 重要性×0.3）与低重要性记忆清理。

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("memory_chunks", sa.Column("importance", sa.Integer(), nullable=False, server_default=sa.text("5")))


def downgrade() -> None:
    op.drop_column("memory_chunks", "importance")
