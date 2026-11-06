"""Reset mixed market cache and isolate sources. Revision 0024, revises 0023."""
from alembic import op
import sqlalchemy as sa

revision = '0024'
down_revision = '0023'
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    db.execute(sa.text("CREATE TABLE market_source_policy (id integer PRIMARY KEY CONSTRAINT ck_market_source_policy_singleton CHECK(id=1), akshare_enabled boolean NOT NULL DEFAULT false, snapshots_enabled boolean NOT NULL DEFAULT false, revision integer NOT NULL DEFAULT 1)"))
    db.execute(sa.text("INSERT INTO market_source_policy(id) VALUES (1)"))
    # Origins were not tracked; discard the application's mixed cache, not the source DB.
    for table in ('kline_15m', 'kline_1d', 'kline_1mon', 'snapshot_realtime',
                  'stock_fundamentals', 'etf_premiums', 'index_valuations', 'kline_quality'):
        db.execute(sa.text(f'TRUNCATE TABLE {table}'))
    db.execute(sa.text("DELETE FROM sync_tasks"))
    db.execute(sa.text("DELETE FROM sync_status WHERE scope IN ('fixed_indices','catalog','watchlist','local_market_sync')"))
    db.execute(sa.text("DELETE FROM task_logs WHERE task_type IN ('kline_init','kline_incremental','kline_backfill','realtime','local_market_sync','catalog')"))
    old = "SELECT id FROM symbols WHERE type='index' AND market<>'SW' AND ((is_fixed_index AND sort_order>8) OR code='' OR code LIKE 'BK%' OR code LIKE '881%')"
    tables = list(db.scalars(sa.text("SELECT c.table_name FROM information_schema.columns c JOIN pg_class p ON p.relname=c.table_name JOIN pg_namespace n ON n.oid=p.relnamespace AND n.nspname=c.table_schema WHERE c.table_schema='public' AND c.column_name='symbol_id' AND p.relkind IN ('r','p') AND NOT p.relispartition")))
    for table in tables:
        db.execute(sa.text(f'DELETE FROM "{table}" WHERE symbol_id IN ({old})'))
    db.execute(sa.text(f'DELETE FROM symbols WHERE id IN ({old})'))
    db.execute(sa.text("UPDATE user_watchlist SET sync_status='pending'"))
    for table in ('kline_15m', 'kline_1d', 'kline_1mon'):
        db.execute(sa.text(f"ALTER TABLE {table} ADD COLUMN source varchar(16) NOT NULL DEFAULT 'stockdb'"))
        db.execute(sa.text(f'ALTER TABLE {table} DROP CONSTRAINT {table}_pkey'))
        db.execute(sa.text(f'ALTER TABLE {table} ADD PRIMARY KEY(symbol_id, ts, source)'))
    db.execute(sa.text("CREATE TABLE kline_1w (LIKE kline_1d INCLUDING DEFAULTS) PARTITION BY RANGE(ts)"))
    db.execute(sa.text("ALTER TABLE kline_1w ADD PRIMARY KEY(symbol_id, ts, source)"))
    db.execute(sa.text("CREATE TABLE kline_1w_default PARTITION OF kline_1w DEFAULT"))


def downgrade():
    raise RuntimeError('Deleted data cannot be restored; resynchronize from the source')
