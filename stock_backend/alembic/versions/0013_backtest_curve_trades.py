"""G32：backtest_results 加 equity_curve / trades 两列（JSONB，可空）。

P1-11 回测结果可视化：引擎已产出资金曲线与买卖流水，但此前只在 metrics 里落库汇总数字，
两条序列用完即弃。本迁移落库供前端渲染资金曲线图与 K 线买卖点标注。

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 存量结果行两列为 NULL，前端按空态降级（不设 server_default，避免回填大 JSON）
    op.add_column(
        "backtest_results",
        sa.Column("equity_curve", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "backtest_results",
        sa.Column("trades", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("backtest_results", "trades")
    op.drop_column("backtest_results", "equity_curve")
