"""Optional history storage and retirement of realtime quote stores."""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('market_source_policy', sa.Column('history_storage_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column('market_source_policy', sa.Column('auto_sync_enabled', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_column('market_source_policy', 'snapshots_enabled')
    op.execute('UPDATE market_source_policy SET revision=revision+1 WHERE id=1')
    for table in ('snapshot_realtime', 'index_valuations', 'stock_fundamentals', 'etf_premiums'):
        op.execute(sa.text('DROP TABLE IF EXISTS ' + table))
    op.execute("DELETE FROM sync_tasks WHERE task_type='realtime'")


def downgrade():
    raise RuntimeError('Retired realtime stores cannot be restored by downgrade')
