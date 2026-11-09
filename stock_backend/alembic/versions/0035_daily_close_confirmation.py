"""Persist whether the daily bar was fetched after its session closed."""

import sqlalchemy as sa
from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep established history. The newest legacy row for each stock/source
    # might have been fetched intraday and must be refreshed before forecasting.
    op.add_column("kline_1d", sa.Column("close_confirmed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.execute("""
        WITH tails AS MATERIALIZED (
            SELECT symbol.id, source.name, tail.ts
            FROM symbols AS symbol
            CROSS JOIN (VALUES ('stockdb'), ('akshare')) AS source(name)
            CROSS JOIN LATERAL (
                SELECT ts FROM kline_1d
                WHERE symbol_id = symbol.id AND kline_1d.source = source.name
                ORDER BY ts DESC LIMIT 1
            ) AS tail
            WHERE symbol.type = 'stock'
        )
        UPDATE kline_1d AS bar SET close_confirmed = false
        FROM tails WHERE bar.symbol_id = tails.id AND bar.source = tails.name AND bar.ts = tails.ts
    """)
    op.alter_column("kline_1d", "close_confirmed", server_default=sa.false())


def downgrade() -> None:
    op.drop_column("kline_1d", "close_confirmed")
