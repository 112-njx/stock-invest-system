"""审计域读写（G15 · P0-3a）：记忆访问日志。

多租户隔离：所有查询强制带 user_id 过滤。写入为 best-effort —— 审计失败不应中断记忆主链路，
故 `log()` 内部吞异常并告警（调用方无需 try）。
"""

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.audit import AuditLog

logger = logging.getLogger(__name__)

# 审计动作枚举
ACTION_READ = "memory_read"
ACTION_WRITE = "memory_write"
ACTION_DELETE = "memory_delete"


def log(db: Session, user_id: int, action: str, memory_id: int | None = None, ip: str | None = None) -> AuditLog | None:
    """记一条审计日志（best-effort：失败只告警，不影响记忆读写主链路）。"""
    try:
        row = AuditLog(user_id=user_id, action=action, memory_id=memory_id, ip=ip)
        db.add(row)
        db.flush()
        return row
    except Exception as e:  # noqa: BLE001
        logger.warning("audit log failed user=%s action=%s: %s", user_id, action, e)
        return None


def list_logs(db: Session, user_id: int, action: str | None = None, offset: int = 0, limit: int = 50) -> list[AuditLog]:
    """按用户倒序分页返回审计日志，支持按动作筛选。"""
    stmt = select(AuditLog).where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return list(db.scalars(stmt.order_by(AuditLog.id.desc()).offset(offset).limit(limit)))


def count_logs(db: Session, user_id: int, action: str | None = None) -> int:
    stmt = select(func.count()).select_from(AuditLog).where(AuditLog.user_id == user_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    return int(db.scalar(stmt) or 0)
