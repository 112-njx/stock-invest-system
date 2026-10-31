"""Durable delivery and recovery for watched A-share K-line sync."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.ops import SyncTask
from app.models.kline_quality import KlineQuality
from app.models.symbol import Symbol
from app.models.user import UserWatchlist
from app.repositories import user_repo
from app.utils.market_cache import as_utc
from app.utils.db import get_session

RETRY_SECONDS = 60
PUBLISH_STALE = timedelta(minutes=30)
RUNNING_STALE = timedelta(hours=2)
ORPHAN_RUNNING = timedelta(minutes=2)


def queue_watchlist_sync(db: Session, symbol_id: int, *, initialize: bool, force: bool = False,
                         now: datetime | None = None) -> SyncTask:
    now = now or datetime.now(UTC)
    kind = "kline_init" if initialize else "kline_incremental"
    db.execute(select(func.pg_advisory_xact_lock(symbol_id)))
    row = db.scalar(select(SyncTask).where(SyncTask.task_type == kind, SyncTask.symbol_id == symbol_id)
                    .with_for_update())
    if row is None:
        row = SyncTask(task_type=kind, symbol_id=symbol_id)
        db.add(row)
    elif not force and row.status in {"queued", "running"} and row.last_run_at and now - as_utc(row.last_run_at) < (
        RUNNING_STALE if row.status == "running" else PUBLISH_STALE
    ):
        user_repo.update_watchlist_sync_status(db, symbol_id, "pending")
        db.commit()
        return row
    elif not force and row.next_run_at and as_utc(row.next_run_at) > now:
        return row
    row.status = "queued"
    row.publish_status = "pending"
    row.celery_task_id = str(uuid4())
    row.last_run_at = now
    row.next_run_at = now
    row.retry_count = 0
    row.last_error = None
    user_repo.update_watchlist_sync_status(db, symbol_id, "pending")
    db.commit()
    return row


def dispatch_watchlist_sync() -> dict:
    """Publish pending rows and recover published rows not started by a worker."""
    from app.worker.tasks.sync_tasks import watchlist_stock_sync

    db = get_session()
    sent = 0
    try:
        now = datetime.now(UTC)
        from app.services.kline_quality_service import last_completed_mainland_day
        from app.worker.celery_app import celery_app

        active = celery_app.control.inspect(timeout=1).active() or {}
        active_ids = {task["id"] for tasks in active.values() for task in tasks}
        expected_day = last_completed_mainland_day(db, now)
        watched = list(db.scalars(select(UserWatchlist.symbol_id).distinct()))
        for symbol_id in watched:
            sym = db.get(Symbol, symbol_id)
            if sym is None:
                continue
            from app.services.kline_quality_service import is_a_share_stock
            from app.repositories import kline_repo

            if not is_a_share_stock(sym):
                continue
            quality = db.get(KlineQuality, (symbol_id, "1d"))
            if quality is not None and quality.status == "complete" and (
                expected_day is None or quality.checked_to is not None and quality.checked_to >= expected_day
            ):
                if db.scalar(select(UserWatchlist.id).where(UserWatchlist.symbol_id == symbol_id,
                                                          UserWatchlist.sync_status != "done").limit(1)):
                    user_repo.update_watchlist_sync_status(db, symbol_id, "done")
                    db.commit()
                continue
            initialize = kline_repo.latest_ts(db, "1d", symbol_id) is None
            kind = "kline_init" if initialize else "kline_incremental"
            row = db.scalar(select(SyncTask).where(SyncTask.task_type == kind,
                                                  SyncTask.symbol_id == symbol_id))
            orphaned = bool(active and row and row.status == "running" and row.last_run_at
                            and now - as_utc(row.last_run_at) >= ORPHAN_RUNNING
                            and row.celery_task_id not in active_ids)
            queue_watchlist_sync(db, symbol_id, initialize=initialize, force=orphaned, now=now)
        rows = list(db.scalars(select(SyncTask).where(
            SyncTask.symbol_id.in_(select(UserWatchlist.symbol_id)),
            SyncTask.task_type.in_(("kline_init", "kline_incremental")),
            SyncTask.status == "queued",
            SyncTask.next_run_at <= now,
        ).order_by(SyncTask.next_run_at).limit(50)))
        for row in rows:
            if row.publish_status == "published" and row.last_run_at and now - as_utc(row.last_run_at) < PUBLISH_STALE:
                continue
            if row.publish_status == "published":
                row.celery_task_id = str(uuid4())
                row.publish_status = "pending"
                db.commit()
            try:
                watchlist_stock_sync.apply_async(
                    kwargs={"symbol_id": row.symbol_id, "initialize": row.task_type == "kline_init"},
                    task_id=row.celery_task_id,
                )
                db.refresh(row)
                if row.status == "queued" and row.publish_status == "pending":
                    row.publish_status = "published"
                    row.last_run_at = now
                db.commit()
                sent += 1
            except Exception as exc:
                row.last_error = str(exc)[:500]
                db.commit()
        return {"published": sent}
    finally:
        db.close()
