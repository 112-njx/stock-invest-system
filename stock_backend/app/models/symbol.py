"""标的统一模型：股票/ETF/指数共用。"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("type", "name", name="uq_symbols_type_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(16), nullable=False, default="")  # 行业指数 code 由同步回填
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    type: Mapped[str] = mapped_column(String(16), nullable=False)  # stock/etf/index
    market: Mapped[str] = mapped_column(String(16), nullable=False, default="SSE")
    industry: Mapped[str | None] = mapped_column(String(64))
    etf_linked: Mapped[str | None] = mapped_column(String(16))
    is_fixed_index: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_catalog: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # 全量目录（未同步K线）
    sort_order: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
