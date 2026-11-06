"""Independent indicator engine policy; SDK is the default."""
from alembic import op
revision = '0031'
down_revision = '0030'
branch_labels = depends_on = None


def upgrade():
    op.execute("CREATE TABLE indicator_settings (id INTEGER PRIMARY KEY CHECK(id=1), pandas_enabled BOOLEAN NOT NULL DEFAULT FALSE, revision INTEGER NOT NULL DEFAULT 1)")
    op.execute("INSERT INTO indicator_settings(id) VALUES(1)")


def downgrade():
    op.drop_table('indicator_settings')
