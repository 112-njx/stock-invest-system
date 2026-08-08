"""运维域：sync_tasks 状态 + task_logs 全链路日志。"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import SyncTask, TaskLog


def upsert_sync_task(
    db: Session,
    task_type: str,
    symbol_id: int | None,
    status: str,
    last_run_at: datetime,
    next_run_at: datetime | None = None,
) -> None:
    """按 (task_type, symbol_id) 幂等更新同步任务状态（无唯一约束，查询-更新/插入）。"""
    stmt = select(SyncTask).where(
        SyncTask.task_type == task_type,
        SyncTask.symbol_id.is_(None) if symbol_id is None else SyncTask.symbol_id == symbol_id,
    )
    row = db.scalar(stmt)
    if row:
        row.status = status
        row.last_run_at = last_run_at
        row.next_run_at = next_run_at
    else:
        db.add(
            SyncTask(
                task_type=task_type,
                symbol_id=symbol_id,
                status=status,
                last_run_at=last_run_at,
                next_run_at=next_run_at,
            )
        )


def log_task(
    db: Session,
    task_type: str,
    task_id: str | None,
    status: str,
    message: str,
    request_id: str | None = None,
) -> None:
    db.add(TaskLog(task_type=task_type, task_id=task_id, request_id=request_id, status=status, message=message))


def latest_sync_task(db: Session, task_type: str, symbol_id: int | None = None) -> SyncTask | None:
    stmt = select(SyncTask).where(SyncTask.task_type == task_type)
    if symbol_id is not None:
        stmt = stmt.where(SyncTask.symbol_id == symbol_id)
    return db.scalar(stmt.order_by(SyncTask.last_run_at.desc()))
