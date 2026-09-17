"""G17（P1-5a）：新增 export_tasks 表，记录用户数据导出任务状态与临时文件位置。

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "export_tasks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_path", sa.String(512), nullable=True),
        sa.Column("file_size", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default="now()"),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_export_tasks"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_export_tasks_user_id_users", ondelete="CASCADE"
        ),
    )
    op.create_index("ix_export_tasks_user_id", "export_tasks", ["user_id"])
    op.create_index("ix_export_tasks_status", "export_tasks", ["status"])


def downgrade() -> None:
    op.drop_index("ix_export_tasks_status", table_name="export_tasks")
    op.drop_index("ix_export_tasks_user_id", table_name="export_tasks")
    op.drop_table("export_tasks")
