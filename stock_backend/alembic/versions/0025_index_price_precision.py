"""Allow the native SDK's long-history synthetic index levels. Revision 0025."""
from alembic import op
import sqlalchemy as sa

revision = '0025'
down_revision = '0024'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('kline_15m', 'kline_1d', 'kline_1w', 'kline_1mon'):
        for column in ('open', 'high', 'low', 'close'):
            op.alter_column(table, column, type_=sa.Numeric(30, 6), existing_nullable=False)


def downgrade():
    raise RuntimeError('Narrowing index prices can lose data')
