"""运维域：sync_tasks 状态 + sync_status 进度 + task_logs 全链路日志。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ops import SyncStatus, SyncTask, TaskLog


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


# ---- sync_status（V0.2 同步进度，供前端轮询）----
def upsert_sync_status(
    db: Session,
    scope: str,
    status: str,
    progress: int,
    total: int,
    message: str | None = None,
    target_id: int | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> None:
    """按 (scope, target_id) 幂等 upsert 同步进度记录。"""
    stmt = select(SyncStatus).where(
        SyncStatus.scope == scope,
        SyncStatus.target_id.is_(None) if target_id is None else SyncStatus.target_id == target_id,
    )
    row = db.scalar(stmt)
    now = datetime.now(UTC)
    if row:
        row.status = status
        row.progress = progress
        row.total = total
        row.message = message
        if started_at is not None:
            row.started_at = started_at
        if finished_at is not None:
            row.finished_at = finished_at
        row.updated_at = now
    else:
        db.add(
            SyncStatus(
                scope=scope,
                target_id=target_id,
                status=status,
                progress=progress,
                total=total,
                message=message,
                started_at=started_at,
                finished_at=finished_at,
            )
        )
    db.flush()


def list_sync_status(db: Session, scope: str | None = None) -> list[SyncStatus]:
    stmt = select(SyncStatus).order_by(SyncStatus.id)
    if scope:
        stmt = stmt.where(SyncStatus.scope == scope)
    return list(db.scalars(stmt))


def get_latest_sync_status(db: Session, scope: str) -> SyncStatus | None:
    """某 scope 最新一条同步状态（前端轮询固定指数/目录/关注同步进度）。"""
    return db.scalar(
        select(SyncStatus).where(SyncStatus.scope == scope).order_by(SyncStatus.id.desc()).limit(1)
    )
