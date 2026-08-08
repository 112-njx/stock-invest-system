"""运维域：行情同步任务状态、全链路任务日志。"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class SyncTask(Base):
    __tablename__ = "sync_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String(32), nullable=False)  # kline_init/kline_incremental/realtime
    symbol_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("symbols.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")  # running/success/failed
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TaskLog(Base):
    __tablename__ = "task_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_type: Mapped[str | None] = mapped_column(String(32))
    task_id: Mapped[str | None] = mapped_column(String(64))  # Celery 任务 ID
    request_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str | None] = mapped_column(String(16))
    message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
