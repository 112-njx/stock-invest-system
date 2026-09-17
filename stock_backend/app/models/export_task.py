"""用户数据导出任务（P1-5a）：记录异步导出状态 + 临时文件位置 + 过期时间。

《个人信息保护法》第四十五条数据复制权：用户可导出全量个人数据。
文件存临时目录，默认 24h 后由 beat 清理任务删除。
"""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ExportTask(Base):
    __tablename__ = "export_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", index=True
    )  # pending / running / success / failed / expired
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0-100
    file_path: Mapped[str | None] = mapped_column(String(512))  # 生成后的 ZIP 绝对路径
    file_size: Mapped[int | None] = mapped_column(BigInteger)  # 字节
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default="now()")
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 文件删除时刻
