"""G02：新增 email_logs 表，记录邮件发送状态（sent/failed/simulated）。

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("recipient", sa.String(255), nullable=False),
        sa.Column("template", sa.String(64), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False, server_default=""),
        sa.Column("status", sa.String(16), nullable=False),  # sent / failed / simulated
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default="now()"),
        sa.PrimaryKeyConstraint("id", name="pk_email_logs"),
    )
    op.create_index("ix_email_logs_recipient", "email_logs", ["recipient"])
    op.create_index("ix_email_logs_created_at", "email_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_email_logs_created_at", table_name="email_logs")
    op.drop_index("ix_email_logs_recipient", table_name="email_logs")
    op.drop_table("email_logs")
