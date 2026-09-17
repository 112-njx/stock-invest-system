"""通知域：站内通知（notifications）+ 系统公告（admin_announcements）。

- notifications：面向单个用户的站内信（系统公告分发 / 回测完成 / Agent 完成 / 安全提醒）。
- admin_announcements：管理员发布的全局公告，前端顶部 banner 展示活跃公告。
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)  # system/backtest_complete/agent_complete/security
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    is_read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AdminAnnouncement(Base):
    __tablename__ = "admin_announcements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False, default="info")  # info/warning/maintenance
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # NULL=永不过期
