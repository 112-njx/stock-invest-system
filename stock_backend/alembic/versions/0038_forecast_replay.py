"""Store historical forecast replay reports."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "forecast_replays",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(6), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("options", JSONB, nullable=False),
        sa.Column("report", JSONB),
        sa.Column("error", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_forecast_replay_owner", "forecast_replays", ["user_id", "symbol", "id"])
    op.create_index("ix_forecast_replay_pending", "forecast_replays", ["status", "id"])
    op.create_index("uq_forecast_replay_active", "forecast_replays", ["user_id"], unique=True,
                    postgresql_where=sa.text("status IN ('queued', 'running')"))


def downgrade():
    op.drop_table("forecast_replays")
