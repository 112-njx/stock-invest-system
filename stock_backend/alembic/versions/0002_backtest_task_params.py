"""backtest_tasks 增加回测参数列（period/start_ts/end_ts/fill_on），使任务自包含可被 worker 执行。

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("backtest_tasks", sa.Column("period", sa.String(length=8), nullable=False, server_default="1d"))
    op.add_column("backtest_tasks", sa.Column("start_ts", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backtest_tasks", sa.Column("end_ts", sa.DateTime(timezone=True), nullable=True))
    op.add_column("backtest_tasks", sa.Column("fill_on", sa.String(length=8), nullable=False, server_default="close"))


def downgrade() -> None:
    op.drop_column("backtest_tasks", "fill_on")
    op.drop_column("backtest_tasks", "end_ts")
    op.drop_column("backtest_tasks", "start_ts")
    op.drop_column("backtest_tasks", "period")
