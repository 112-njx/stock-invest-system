"""Durable administrator-triggered import from the manually updated local data source."""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, select, text

from app.models.forecast import ForecastTracking
from app.models.ops import SyncTask
from app.models.symbol import Symbol
from app.models.user import User, UserWatchlist
from app.repositories import ops_repo
from app.utils.db import get_session

TASK_TYPE = "local_market_sync"
LOCK_KEY = 6100000001
logger = logging.getLogger(__name__)


def _sync_targets(db):
    regular = Symbol.is_fixed_index.is_(True) | Symbol.id.in_(select(UserWatchlist.symbol_id))
    tracked_codes = select(ForecastTracking.symbol).join(User, User.id == ForecastTracking.user_id).where(
        User.is_deleted.is_(False),
    )
    tracked = and_(Symbol.type == "stock", Symbol.market.in_(("SSE", "SZSE", "BSE")), Symbol.code.in_(tracked_codes))
    return db.execute(select(Symbol, regular).where(regular | tracked).order_by(Symbol.id)).all()


def request_sync() -> dict:
    db = get_session()
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        import os
        if os.environ.get('STOCKDB_CONTROL_DIR'):
            from .stockdb_files import ensure_available
            from .stockdb_update import directory
            from fastapi import HTTPException
            try:
                ensure_available(directory())
            except RuntimeError as exc:
                raise HTTPException(409, str(exc)) from exc
        row = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE).with_for_update())
        if row and row.status in {"queued", "running"}:
            return {"task_id": row.celery_task_id, "status": row.status}
        if row is None:
            row = SyncTask(task_type=TASK_TYPE)
            db.add(row)
        row.status = "queued"
        row.publish_status = "pending"
        row.celery_task_id = str(uuid4())
        row.last_run_at = datetime.now(UTC)
        row.next_run_at = row.last_run_at
        row.last_error = None
        ops_repo.upsert_sync_status(db, TASK_TYPE, "queued", 0, 0, "等待同步本地行情", started_at=row.last_run_at)
        db.commit()
        return {"task_id": row.celery_task_id, "status": row.status}
    finally:
        db.close()


def dispatch(active_ids: set[str], workers_responded: bool) -> None:
    """Republish interrupted deliveries and recover work after a worker disappears."""
    from app.worker.tasks.sync_tasks import local_market_sync

    db = get_session()
    try:
        db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": LOCK_KEY})
        row = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE).with_for_update())
        if row is None or row.status not in {"queued", "running"}:
            return
        from app.utils.market_cache import as_utc

        age = datetime.now(UTC) - as_utc(row.last_run_at)
        if row.status == "running":
            if not workers_responded or row.celery_task_id in active_ids or age < timedelta(hours=2):
                return
            row.status = "queued"
            row.publish_status = "pending"
        if row.publish_status == "published" and age < timedelta(minutes=30):
            return
        local_market_sync.apply_async(task_id=row.celery_task_id)
        row.publish_status = "published"
        row.last_run_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()


def run(task_id: str) -> dict:
    from app.data_providers.stockdb import StockDBProvider
    from app.services import sync_service
    from app.utils.db import engine

    connection = engine.connect()
    locked = connection.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": LOCK_KEY + 1}).scalar()
    if not locked:
        connection.close()
        return {"skipped": "another manual sync is running"}
    db = get_session()
    try:
        row = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE))
        if row is None or row.celery_task_id != task_id or row.status not in {"queued", "running"}:
            return {"skipped": "stale delivery"}
        row.status, row.publish_status = "running", "started"
        row.last_run_at = datetime.now(UTC)
        db.commit()
        from app.core.config import get_settings
        from app.data_providers.base import ProviderError
        from app.data_providers.factory import get_provider
        from app.services.market_policy import akshare_enabled

        try:
            source_day = StockDBProvider().latest_day()
        except (ProviderError, ValueError) as exc:
            if not akshare_enabled():
                raise RuntimeError('本地服务连接失败，AkShare 兜底未启用') from exc
            logger.warning("manual sync local_connection_error, using AkShare fallback: %s", exc)
            source_day = None
        if source_day is None and not akshare_enabled():
            raise RuntimeError('本地服务没有可用行情数据，AkShare 兜底未启用')
        if source_day is not None:
            try:
                StockDBProvider().refresh_sdk()
            except ProviderError as exc:
                logger.warning('SDK 7900 unavailable; continuing supported RD queries: %s', exc)
        target_day = source_day or datetime.now(get_settings().tz).date()
        source_label = f"本地源日期 {source_day}" if source_day else f"本地源不可用，AkShare 请求截至 {target_day}"
        from app.services import market_policy
        market_policy.invalidate_caches()
        get_provider().probe()
        catalog = sync_service.run_catalog_sync(force=True)
        if catalog.get("status") == "partial":
            raise RuntimeError("所有数据源均未返回证券目录，请稍后重试")
        symbols = [(sym, regular) for sym, regular in _sync_targets(db) if sync_service.supported_symbol(sym)]
        failed = []
        changed = 0
        end = datetime.combine(target_day, datetime.max.time(), get_settings().tz).astimezone(UTC)
        start = end - timedelta(days=get_settings().KLINE_INIT_DAYS)
        for number, (symbol, regular) in enumerate(symbols, 1):
            try:
                if regular:
                    result = sync_service.run_kline_init(symbol_id=symbol.id, end=end)
                    changed += sum(sum(periods.values()) for periods in result.values())
                else:
                    with get_session() as history_db:
                        result = sync_service.prepare_history_window(history_db, symbol, "1d", start, end, initial=True)
                        changed += result["added"]
            except Exception as exc:
                failed.append(f"{symbol.name}: {str(exc)[:120]}")
            ops_repo.upsert_sync_status(
                db, TASK_TYPE, "running", int(number / len(symbols) * 100), len(symbols),
                f"{source_label}，已处理 {number}/{len(symbols)}，更新 {changed} 条，失败 {len(failed)} 个",
            )
            db.commit()
        row.status = "success" if not failed else "failed"
        row.publish_status = "completed"
        row.last_error = "；".join(failed) or None
        message = f"{source_label}，处理 {len(symbols)} 个标的，更新 {changed} 条，失败 {len(failed)} 个"
        ops_repo.upsert_sync_status(db, TASK_TYPE, "partial" if failed else "done", 100, len(symbols),
                                    message, finished_at=datetime.now(UTC))
        db.commit()
        return {"source_date": source_day.isoformat() if source_day else None,
                "changed": changed, "failed": failed}
    except Exception as exc:
        db.rollback()
        row = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE))
        if row and row.celery_task_id == task_id:
            row.status, row.publish_status, row.last_error = "failed", "completed", str(exc)[:2000]
            ops_repo.upsert_sync_status(db, TASK_TYPE, "failed", 0, 0, str(exc)[:500], finished_at=datetime.now(UTC))
            db.commit()
        raise
    finally:
        db.close()
        connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": LOCK_KEY + 1})
        connection.close()


def status(db) -> dict:
    row = db.scalar(select(SyncTask).where(SyncTask.task_type == TASK_TYPE))
    progress = ops_repo.get_latest_sync_status(db, TASK_TYPE)
    return {"status": row.status if row else "idle", "task_id": row.celery_task_id if row else None,
            "error": row.last_error if row else None, "progress": progress.progress if progress else 0,
            "message": progress.message if progress else "尚未同步本地行情"}
