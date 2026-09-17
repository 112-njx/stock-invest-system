"""V0.3 G15（P0-3a）：新建 audit_log 表（记忆访问审计）。

记录每次记忆读取 / 写入 / 删除，供用户自查与合规追溯（P0-3 隐私合规要求）。
- user_id FK → users.id ON DELETE CASCADE（账户硬删时审计一并清除，避免孤儿行）；
- action varchar(32)：memory_read / memory_write / memory_delete；
- memory_id bigint 可空：关联 memory_chunks.id，批量操作（清空）为空；
- ip varchar(64) 可空：后台任务无请求上下文时为空；
- 复合索引 (user_id, created_at DESC)：按用户倒序翻页是唯一查询形态。

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("memory_id", sa.BigInteger(), nullable=True),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_user_created", "audit_log", ["user_id", sa.text("created_at DESC")])


def downgrade() -> None:
    op.drop_index("ix_audit_log_user_created", table_name="audit_log")
    op.drop_table("audit_log")
