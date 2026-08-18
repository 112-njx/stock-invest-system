"""snapshot_realtime.volume/amount 允许 NULL（海外指数无成交量/额字段，用 NULL 区分"数据缺失"与"真实零成交"）。

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("snapshot_realtime", "volume", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("snapshot_realtime", "amount", existing_type=sa.Numeric(20, 2), nullable=True)


def downgrade() -> None:
    op.alter_column("snapshot_realtime", "volume", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("snapshot_realtime", "amount", existing_type=sa.Numeric(20, 2), nullable=False)
