from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MarketIndexBar(Base):
    """History owned by the eight headline indices on the market page."""

    __tablename__ = "market_index_bars"
    __table_args__ = (
        CheckConstraint("period IN ('1d', '15m', '1w', '1mon')", name="ck_market_index_bar_period"),
        CheckConstraint("source IN ('qmt', 'eastmoney', 'sina')", name="ck_market_index_bar_source"),
    )

    symbol_id: Mapped[int] = mapped_column(ForeignKey("symbols.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(4), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    high: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    low: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    close: Mapped[Decimal] = mapped_column(Numeric(30, 6))
    pre_close: Mapped[Decimal | None] = mapped_column(Numeric(30, 6))
    volume: Mapped[int] = mapped_column(BigInteger)
    amount: Mapped[Decimal] = mapped_column(Numeric(24, 2))
    source: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.clock_timestamp(), index=True)
