"""Store forecast runs and tracking cursors."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecast_runs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("symbol", sa.String(6), nullable=False),
        sa.Column("data_version", sa.String(64), nullable=False),
        sa.Column("trigger", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("diagnosis", JSONB),
        sa.Column("prediction", JSONB),
        sa.Column("models", JSONB, nullable=False),
        sa.Column("error", sa.String(240)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("user_id", "symbol", "data_version", name="uq_forecast_input"),
    )
    op.create_index("ix_forecast_history", "forecast_runs", ["user_id", "symbol", "id"])
    op.create_index("ix_forecast_delivery", "forecast_runs", ["status", "updated_at"])
    op.create_table(
        "forecast_tracking",
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("symbol", sa.String(6), primary_key=True),
        sa.Column("last_session", sa.Date),
        sa.Column("next_check_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_forecast_tracking_due", "forecast_tracking", ["next_check_at"])


def downgrade() -> None:
    op.drop_table("forecast_tracking")
    op.drop_table("forecast_runs")
