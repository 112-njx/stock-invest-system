"""导出任务读写（G17）：状态机 + 过期扫描。所有查询强制 user_id 隔离。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.export_task import ExportTask


def create(db: Session, user_id: int, expires_at: datetime | None = None) -> ExportTask:
    row = ExportTask(user_id=user_id, status="pending", progress=0, expires_at=expires_at)
    db.add(row)
    db.flush()
    return row


def get(db: Session, task_id: int) -> ExportTask | None:
    return db.get(ExportTask, task_id)


def get_owned(db: Session, user_id: int, task_id: int) -> ExportTask | None:
    """按 id 取任务（强制 user_id 归属校验，防越权查询他人导出）。"""
    return db.scalar(select(ExportTask).where(ExportTask.id == task_id, ExportTask.user_id == user_id))


def list_for_user(db: Session, user_id: int, limit: int = 20) -> list[ExportTask]:
    stmt = (
        select(ExportTask)
        .where(ExportTask.user_id == user_id)
        .order_by(ExportTask.created_at.desc(), ExportTask.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def update_status(
    db: Session,
    row: ExportTask,
    status: str,
    progress: int | None = None,
    file_path: str | None = None,
    file_size: int | None = None,
    error: str | None = None,
) -> None:
    row.status = status
    if progress is not None:
        row.progress = progress
    if file_path is not None:
        row.file_path = file_path
    if file_size is not None:
        row.file_size = file_size
    if error is not None:
        row.error = error[:2000]
    if status in ("success", "failed", "expired"):
        row.finished_at = datetime.now(UTC)
    db.flush()


def list_expired(db: Session, now: datetime | None = None) -> list[ExportTask]:
    """已过保留期且文件可能仍在的任务（供 beat 清理）。"""
    now = now or datetime.now(UTC)
    stmt = select(ExportTask).where(
        ExportTask.expires_at.is_not(None),
        ExportTask.expires_at <= now,
        ExportTask.status != "expired",
    )
    return list(db.scalars(stmt))
