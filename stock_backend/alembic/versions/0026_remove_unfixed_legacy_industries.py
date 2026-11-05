"""Remove legacy industries outside the fixed home list. Revision 0026."""
from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    old = "SELECT id FROM symbols WHERE type='index' AND market<>'SW' AND ((is_fixed_index AND sort_order>8) OR code='' OR code LIKE 'BK%' OR code LIKE '881%')"
    tables = list(db.scalars(sa.text("SELECT c.table_name FROM information_schema.columns c JOIN pg_class p ON p.relname=c.table_name JOIN pg_namespace n ON n.oid=p.relnamespace AND n.nspname=c.table_schema WHERE c.table_schema='public' AND c.column_name='symbol_id' AND p.relkind IN ('r','p') AND NOT p.relispartition")))
    for table in tables:
        db.execute(sa.text(f'DELETE FROM "{table}" WHERE symbol_id IN ({old})'))
    db.execute(sa.text(f'DELETE FROM symbols WHERE id IN ({old})'))


def downgrade():
    raise RuntimeError('Deleted legacy industries cannot be restored')
