"""Deduplicate sync tasks and persist delivery state.

Revision ID: 0022
Revises: 0021
"""

from alembic import op
import sqlalchemy as sa

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""DELETE FROM sync_tasks s USING (
        SELECT id, row_number() OVER (PARTITION BY task_type, symbol_id
            ORDER BY last_run_at DESC NULLS LAST, id DESC) AS rn
        FROM sync_tasks WHERE symbol_id IS NOT NULL
    ) duplicates WHERE s.id = duplicates.id AND duplicates.rn > 1""")
    op.create_index("uq_sync_tasks_type_symbol", "sync_tasks", ["task_type", "symbol_id"],
                    unique=True, postgresql_where=sa.text("symbol_id IS NOT NULL"))
    op.add_column("sync_tasks", sa.Column("celery_task_id", sa.String(64)))
    op.add_column("sync_tasks", sa.Column("publish_status", sa.String(16)))
    op.add_column("sync_tasks", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("sync_tasks", sa.Column("last_error", sa.Text()))


def downgrade() -> None:
    op.drop_column("sync_tasks", "last_error")
    op.drop_column("sync_tasks", "retry_count")
    op.drop_column("sync_tasks", "publish_status")
    op.drop_column("sync_tasks", "celery_task_id")
    op.drop_index("uq_sync_tasks_type_symbol", "sync_tasks")
