"""K 线分区表（按月分区）：各周期直接保存数据源返回值。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, PrimaryKeyConstraint, String, false
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class KlineMixin:
    """K 线公共列；父表按 ts 分区，PK(symbol_id, ts, source) 天然幂等去重。"""

    symbol_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), primary_key=True, default="stockdb", server_default="stockdb")
    open: Mapped[Decimal] = mapped_column(Numeric(30, 6), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(30, 6), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(30, 6), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(30, 6), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False, default=0)


class Kline15m(KlineMixin, Base):
    __tablename__ = "kline_15m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1d(KlineMixin, Base):
    __tablename__ = "kline_1d"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})
    close_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=false())


class Kline1mon(KlineMixin, Base):
    __tablename__ = "kline_1mon"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1w(KlineMixin, Base):
    __tablename__ = "kline_1w"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline1m(KlineMixin, Base):
    __tablename__ = "kline_1m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline5m(KlineMixin, Base):
    __tablename__ = "kline_5m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline30m(KlineMixin, Base):
    __tablename__ = "kline_30m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


class Kline60m(KlineMixin, Base):
    __tablename__ = "kline_60m"
    __table_args__ = (PrimaryKeyConstraint("symbol_id", "ts", "source"), {"postgresql_partition_by": "RANGE (ts)"})


# 周期 → 模型映射
KLINE_MODELS = {
    "1m": Kline1m,
    "5m": Kline5m,
    "30m": Kline30m,
    "60m": Kline60m,

    "1w": Kline1w,
    "15m": Kline15m,
    "1d": Kline1d,
    "1mon": Kline1mon,
}

KLINE_TABLE_NAMES = tuple(KLINE_MODELS.keys())
