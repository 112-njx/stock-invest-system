"""Retire the unreferenced calendar used by the removed gap-repair workflow."""
from alembic import op
import sqlalchemy as sa

revision = '0030'
down_revision = '0029'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('cn_trading_days')
    op.execute('UPDATE market_source_policy SET revision=revision+1 WHERE id=1')


def downgrade():
    op.create_table('cn_trading_days', sa.Column('day', sa.Date(), primary_key=True))
