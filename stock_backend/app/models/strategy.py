"""策略/AI 域：会话、消息、交易策略、回测任务与结果。"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="新会话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user/assistant/system
    symbol_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class TradingStrategy(Base):
    __tablename__ = "trading_strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    code: Mapped[str | None] = mapped_column(Text)
    params: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="draft")  # active/draft
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class BacktestTask(Base):
    __tablename__ = "backtest_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trading_strategies.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")  # queued/running/success/failed
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")


class BacktestResult(Base):
    __tablename__ = "backtest_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("backtest_tasks.id", ondelete="CASCADE"), nullable=False
    )
    strategy_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trading_strategies.id", ondelete="CASCADE"), nullable=False
    )
    symbol_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"), nullable=False)
    win_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    profit_loss_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sharpe: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    total_buys: Mapped[int | None] = mapped_column(Integer)
    total_sells: Mapped[int | None] = mapped_column(Integer)
    annual_return: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    metrics_json: Mapped[dict | None] = mapped_column(JSON)
    start_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
