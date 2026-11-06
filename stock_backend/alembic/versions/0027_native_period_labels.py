"""Keep the native final label for each source period. Revision 0027."""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    if db.scalar(sa.text("SELECT count(*) FROM pg_constraint WHERE conrelid='market_source_policy'::regclass AND conname='market_source_policy_id_check'")):
        db.execute(sa.text("ALTER TABLE market_source_policy RENAME CONSTRAINT market_source_policy_id_check TO ck_market_source_policy_singleton"))
    for table, unit in [('kline_1w', 'week'), ('kline_1mon', 'month')]:
        op.get_bind().execute(sa.text(f"""
            DELETE FROM {table} current USING (
                SELECT symbol_id, source, ts, row_number() OVER (
                    PARTITION BY symbol_id, source, date_trunc('{unit}', ts) ORDER BY ts DESC
                ) AS position FROM {table}
            ) duplicates WHERE duplicates.position > 1
                AND current.symbol_id=duplicates.symbol_id
                AND current.source=duplicates.source AND current.ts=duplicates.ts
        """))


def downgrade():
    raise RuntimeError('Discarded interim labels cannot be restored')
