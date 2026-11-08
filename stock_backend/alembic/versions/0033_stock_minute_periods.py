"""Add stock minute candle partitions."""
from alembic import op

revision = '0033'
down_revision = '0032'
branch_labels = None
depends_on = None


def upgrade():
    for period in ('1m', '5m', '30m', '60m'):
        table = 'kline_' + period
        op.execute(f'CREATE TABLE {table} (LIKE kline_15m INCLUDING DEFAULTS) PARTITION BY RANGE(ts)')
        op.execute(f'ALTER TABLE {table} ADD PRIMARY KEY(symbol_id, ts, source)')
        op.execute(f'CREATE TABLE {table}_default PARTITION OF {table} DEFAULT')


def downgrade():
    for period in ('1m', '5m', '30m', '60m'):
        op.execute('DROP TABLE kline_' + period + ' CASCADE')
