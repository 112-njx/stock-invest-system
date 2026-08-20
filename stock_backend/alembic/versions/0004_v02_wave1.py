"""V0.2 第一波 schema 扩展：管理员、同步状态、标的目录、关注同步状态。

- users.is_admin：管理端点（Provider 健康 / 目录同步）鉴权。
- sync_status：固定指数/关注/目录等同步进度（前端轮询展示）。
- symbols.is_catalog + (is_catalog,type) 索引：全量标的目录预同步。
- user_watchlist.sync_status/last_synced_at：关注添加自动同步状态。

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_table(
        "sync_status",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("target_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("progress", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.add_column("symbols", sa.Column("is_catalog", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_index("ix_symbols_is_catalog_type", "symbols", ["is_catalog", "type"], unique=False)
    op.add_column(
        "user_watchlist",
        sa.Column("sync_status", sa.String(length=16), nullable=False, server_default=sa.text("'pending'")),
    )
    op.add_column("user_watchlist", sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_watchlist", "last_synced_at")
    op.drop_column("user_watchlist", "sync_status")
    op.drop_index("ix_symbols_is_catalog_type", table_name="symbols")
    op.drop_column("symbols", "is_catalog")
    op.drop_table("sync_status")
    op.drop_column("users", "is_admin")
