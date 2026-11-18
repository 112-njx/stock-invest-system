"""Remove persisted AkShare history and configure StockDB updates."""

import sqlalchemy as sa
from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None

TABLES = ("kline_1d", "kline_1w", "kline_1mon", "kline_1m", "kline_5m",
          "kline_15m", "kline_30m", "kline_60m")


def upgrade():
    for name in TABLES:
        table = sa.table(name, sa.column("source", sa.String()))
        op.execute(table.delete().where(table.c.source == "akshare"))
    op.drop_column("market_source_policy", "history_storage_enabled")
    op.alter_column("market_source_policy", "auto_sync_enabled", new_column_name="auto_update_enabled")
    op.execute("UPDATE market_source_policy SET auto_update_enabled = false, revision = revision + 1")


def downgrade():
    # Historical AkShare rows require a restore from the pre-upgrade backup.
    op.alter_column("market_source_policy", "auto_update_enabled", new_column_name="auto_sync_enabled")
    op.add_column("market_source_policy", sa.Column("history_storage_enabled", sa.Boolean(),
                                                   nullable=False, server_default=sa.false()))
    op.execute("UPDATE market_source_policy SET auto_sync_enabled = false, revision = revision + 1")
