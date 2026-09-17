"""邮件日志表：记录每次邮件发送的状态（成功/失败/模拟），供审计和排错。"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class EmailLog(Base):
    __tablename__ = "email_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False, index=True)  # 收件人邮箱
    template: Mapped[str] = mapped_column(String(64), nullable=False)  # 模板名称（verify_email/password_reset/...）
    subject: Mapped[str] = mapped_column(String(255), nullable=False, default="")  # 邮件主题
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # sent / failed / simulated
    error: Mapped[str | None] = mapped_column(Text)  # 失败时的错误信息
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_utcnow)
