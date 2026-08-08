"""实时快照与三类资产特殊数据。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SnapshotRealtime(Base):
    __tablename__ = "snapshot_realtime"

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    change: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    change_pct: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False, default=0)
    open: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    high: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    low: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    pre_close: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)
    turnover: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    amplitude: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class StockFundamental(Base):
    __tablename__ = "stock_fundamentals"

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    market_cap: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class EtfPremium(Base):
    __tablename__ = "etf_premiums"

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    nav: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    premium: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class IndexValuation(Base):
    __tablename__ = "index_valuations"

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pe: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
