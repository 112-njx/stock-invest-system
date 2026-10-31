"""Drop the obsolete materialized weekly K-line table.

Revision ID: 0021
Revises: 0020
"""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS kline_1w CASCADE")


def downgrade() -> None:
    op.execute("""CREATE TABLE kline_1w (
        symbol_id BIGINT NOT NULL REFERENCES symbols(id) ON DELETE CASCADE,
        ts TIMESTAMP NOT NULL,
        open NUMERIC(12,3) NOT NULL,
        high NUMERIC(12,3) NOT NULL,
        low NUMERIC(12,3) NOT NULL,
        close NUMERIC(12,3) NOT NULL,
        volume BIGINT NOT NULL DEFAULT 0,
        amount NUMERIC(20,2) NOT NULL DEFAULT 0,
        PRIMARY KEY (symbol_id, ts)
    ) PARTITION BY RANGE (ts)""")
    op.execute("CREATE TABLE kline_1w_default PARTITION OF kline_1w DEFAULT")
