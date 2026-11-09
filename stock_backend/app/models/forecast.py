"""User-owned forecast runs and opt-in tracking."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (
        UniqueConstraint("user_id", "symbol", "data_version", name="uq_forecast_input"),
        Index("ix_forecast_history", "user_id", "symbol", "id"),
        Index("ix_forecast_delivery", "status", "updated_at"),
        Index("ix_forecast_pending_delivery", "next_delivery_at", postgresql_where=text("status = 'queued'")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(6))
    data_version: Mapped[str] = mapped_column(String(64))
    trigger: Mapped[str] = mapped_column(String(8))
    status: Mapped[str] = mapped_column(String(16))
    next_delivery_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snapshot: Mapped[dict] = mapped_column(JSONB)
    diagnosis: Mapped[dict | None] = mapped_column(JSONB)
    prediction: Mapped[dict | None] = mapped_column(JSONB)
    models: Mapped[dict] = mapped_column(JSONB, default=dict)
    error: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastTracking(Base):
    __tablename__ = "forecast_tracking"
    __table_args__ = (Index("ix_forecast_tracking_due", "next_check_at"),)

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    symbol: Mapped[str] = mapped_column(String(6), primary_key=True)
    last_session: Mapped[date | None] = mapped_column(Date)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ForecastReplay(Base):
    __tablename__ = "forecast_replays"
    __table_args__ = (
        Index("ix_forecast_replay_owner", "user_id", "symbol", "id"),
        Index("ix_forecast_replay_pending", "status", "id"),
        Index("uq_forecast_replay_active", "user_id", unique=True,
              postgresql_where=text("status IN ('queued', 'running')")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    symbol: Mapped[str] = mapped_column(String(6))
    status: Mapped[str] = mapped_column(String(16))
    options: Mapped[dict] = mapped_column(JSONB)
    report: Mapped[dict | None] = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
