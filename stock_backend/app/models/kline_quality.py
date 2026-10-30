"""A 股交易日历与日 K 缺口检查结果。"""

from datetime import date, datetime

from sqlalchemy import JSON, BigInteger, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class TradingDay(Base):
    __tablename__ = "cn_trading_days"

    day: Mapped[date] = mapped_column(Date, primary_key=True)


class KlineQuality(Base):
    __tablename__ = "kline_quality"

    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"), primary_key=True)
    period: Mapped[str] = mapped_column(String(8), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    checked_from: Mapped[date | None] = mapped_column(Date)
    checked_to: Mapped[date | None] = mapped_column(Date)
    missing_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    recovered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    missing_ranges: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
