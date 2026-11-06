"""Shared synthetic candle display coefficient; revision 0028."""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('market_source_policy', sa.Column('synthetic_wick_factor', sa.Float(), nullable=False, server_default='0.5'))
    op.create_check_constraint(op.f('ck_market_source_policy_wick_factor'), 'market_source_policy', 'synthetic_wick_factor >= 0 AND synthetic_wick_factor <= 1')


def downgrade():
    op.drop_constraint(op.f('ck_market_source_policy_wick_factor'), 'market_source_policy', type_='check')
    op.drop_column('market_source_policy', 'synthetic_wick_factor')
