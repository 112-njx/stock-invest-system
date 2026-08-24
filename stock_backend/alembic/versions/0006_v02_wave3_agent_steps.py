"""V0.2 第三波（阶段七）：多智能体可观测性字段。

- agent_steps.summary：节点输出摘要（VARCHAR 500）
- agent_steps.duration_ms：节点耗时（毫秒）
- agent_steps.status：节点状态（running/done/failed，默认 done）
- agent_runs.duration_ms：整次运行总耗时（毫秒）

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("agent_steps", sa.Column("summary", sa.String(length=500), nullable=True))
    op.add_column("agent_steps", sa.Column("duration_ms", sa.Integer(), nullable=True))
    op.add_column("agent_steps", sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'done'")))
    op.add_column("agent_runs", sa.Column("duration_ms", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("agent_runs", "duration_ms")
    op.drop_column("agent_steps", "status")
    op.drop_column("agent_steps", "duration_ms")
    op.drop_column("agent_steps", "summary")
