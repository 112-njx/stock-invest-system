"""审计域（G15 · P0-3a）：记忆访问审计日志。

记录每次记忆的读取 / 写入 / 删除，供用户自查与合规追溯。多租户隔离：所有查询强制带 user_id。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)  # memory_read/memory_write/memory_delete
    memory_id: Mapped[int | None] = mapped_column(BigInteger)  # 关联 memory_chunks.id（清空等批量操作可为空）
    ip: Mapped[str | None] = mapped_column(String(64))  # 请求来源 IP（后台任务无请求上下文时为空）
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
