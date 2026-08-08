"""K 线分区表（按月分区）：四周期共用同一结构。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, PrimaryKeyConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class KlineMixin:
    """K 线公共列；父表按 ts 分区，PK(symbol_id, ts) 天然幂等去重。"""

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)


class Kline15m(KlineMixin, Base):
    __tablename__ = "kline_15m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1d(KlineMixin, Base):
    __tablename__ = "kline_1d"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1w(KlineMixin, Base):
    __tablename__ = "kline_1w"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1mon(KlineMixin, Base):
    __tablename__ = "kline_1mon"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts"), {"postgresql_partition_by": "RANGE (ts)"})


# 周期 → 模型映射
KLINE_MODELS = {
    "15m": Kline15m,
    "1d": Kline1d,
    "1w": Kline1w,
    "1mon": Kline1mon,
}

KLINE_TABLE_NAMES = tuple(KLINE_MODELS.keys())
