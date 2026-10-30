"""Persist mainland trading days and index K-line quality.

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("cn_trading_days", sa.Column("day", sa.Date(), primary_key=True))
    op.create_table(
        "kline_quality",
        sa.Column("symbol_id", sa.BigInteger(), sa.ForeignKey("symbols.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("period", sa.String(8), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("checked_from", sa.Date()),
        sa.Column("checked_to", sa.Date()),
        sa.Column("missing_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recovered", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("missing_ranges", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("kline_quality")
    op.drop_table("cn_trading_days")
