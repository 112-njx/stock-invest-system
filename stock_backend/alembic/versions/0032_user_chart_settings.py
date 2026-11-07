"""Account-specific detail chart preferences."""
from alembic import op
revision = '0032'
down_revision = '0031'
branch_labels = depends_on = None

def upgrade():
    op.execute("CREATE TABLE user_chart_settings (user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE, settings JSONB NOT NULL)")

def downgrade():
    op.drop_table('user_chart_settings')
