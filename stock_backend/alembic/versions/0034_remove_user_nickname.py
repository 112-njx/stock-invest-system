"""Remove the user nickname field and its stored values."""

import sqlalchemy as sa
from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("users", "nickname")


def downgrade() -> None:
    op.add_column("users", sa.Column("nickname", sa.String(64), nullable=True))
