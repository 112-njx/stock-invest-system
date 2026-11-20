"""Retire the indicator engine switch."""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = depends_on = None


def upgrade():
    op.drop_table("indicator_settings")


def downgrade():
    op.execute(
        "CREATE TABLE indicator_settings (id INTEGER PRIMARY KEY CHECK(id=1), "
        "pandas_enabled BOOLEAN NOT NULL DEFAULT FALSE, revision INTEGER NOT NULL DEFAULT 1)"
    )
    op.execute("INSERT INTO indicator_settings(id) VALUES (1)")
