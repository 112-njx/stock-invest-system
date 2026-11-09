"""Track when a queued forecast is eligible for delivery."""

import sqlalchemy as sa
from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("forecast_runs", sa.Column("next_delivery_at", sa.DateTime(timezone=True)))
    op.execute("UPDATE forecast_runs SET next_delivery_at = now() WHERE status = 'queued'")
    op.create_index(
        "ix_forecast_pending_delivery", "forecast_runs", ["next_delivery_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )


def downgrade() -> None:
    op.drop_index("ix_forecast_pending_delivery", table_name="forecast_runs")
    op.drop_column("forecast_runs", "next_delivery_at")
