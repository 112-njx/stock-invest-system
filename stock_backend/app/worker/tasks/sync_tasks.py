"""行情同步 Celery 任务：历史初始化、历史补拉和手动/定时同步。

任务内只做薄编排：调用同步服务，状态与全链路日志写 sync_tasks / task_logs。
"""

import logging
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select, text

from app.core.request_id import get_request_id
from app.models.user import UserWatchlist
from app.services import sync_service
from app.utils.db import engine, get_session
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _log(task_type: str, task_id: str, status: str, message: str) -> None:
    from app.repositories import ops_repo

    db = get_session()
    try:
        ops_repo.log_task(db, task_type, task_id, status, message, request_id=get_request_id())
        db.commit()
    finally:
        db.close()


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_init")
def kline_init(self, symbol_id: int | None = None, days: int | None = None) -> dict:
    """首次全量历史K线（可指定标的或全部）。"""
    _log("kline_init", self.request.id, "running", f"start symbol_id={symbol_id} days={days}")
    try:
        result = sync_service.run_kline_init(symbol_id=symbol_id, days=days)
        _log("kline_init", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_init failed")
        _log("kline_init", self.request.id, "failed", str(exc))
        raise


@celery_app.task(name="app.worker.tasks.sync_tasks.update_stockdb_daily")
def update_stockdb_daily() -> dict:
    from datetime import datetime
    from fastapi import HTTPException
    from app.core.config import get_settings
    from app.services import market_policy, stockdb_update

    if not market_policy.read()["auto_update_enabled"]:
        return {"skipped": "automatic StockDB update disabled"}
    try:
        return stockdb_update.request_update(scheduled_day=datetime.now(get_settings().tz).date().isoformat())
    except HTTPException as exc:
        if exc.status_code == 409:
            return {"skipped": exc.detail}
        raise


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_backfill",
                 acks_late=True, reject_on_worker_lost=True,
                 soft_time_limit=900, time_limit=1200)
def kline_backfill(self, symbol_id: int, period: str, start_iso: str, end_iso: str, initial: bool = False) -> dict:
    """按用户请求的历史窗口补取，结果供前端轮询。"""
    from datetime import datetime

    from app.models.symbol import Symbol
    from app.services.sync_service import prepare_history_window

    db = get_session()
    try:
        sym = db.get(Symbol, symbol_id)
        if sym is None:
            return {"fetched": 0, "added": 0}
        result = prepare_history_window(db, sym, period, datetime.fromisoformat(start_iso),
                                        datetime.fromisoformat(end_iso), initial=initial)
        _log("kline_backfill", self.request.id, "success", f"symbol_id={symbol_id} fetched={result['fetched']}")
        return result
    except Exception as exc:
        db.rollback()
        if self.request.retries < 2:
            raise self.retry(exc=exc, countdown=10, max_retries=2)
        from app.utils.redis_client import get_redis_client

        key = f"kline-backfill:{symbol_id}:{period}:{start_iso}:{end_iso}"
        if initial:
            key += ":initial"
        redis = get_redis_client()
        if redis.get(key) == self.request.id:
            redis.delete(key)
        _log("kline_backfill", self.request.id, "failed", f"symbol_id={symbol_id}: {exc}")
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_init_fixed_indices",
                 acks_late=True, reject_on_worker_lost=True,
                 soft_time_limit=6000, time_limit=6300)
def kline_init_fixed_indices(self) -> dict:
    """固定指数预同步：同步当前固定大盘/行业指数，进度写 sync_status。"""
    from app.utils.redis_client import get_redis_client

    redis = get_redis_client()
    redis.delete('provider:fixed-indices-retry')
    lock_conn = engine.connect()
    if not lock_conn.execute(text("SELECT pg_try_advisory_lock(4000000001)")).scalar():
        lock_conn.close()
        raise self.retry(countdown=30, max_retries=None)
    _log("kline_init", self.request.id, "running", "fixed indices presync start")
    try:
        result = sync_service.run_fixed_indices_sync()
        from app.repositories import ops_repo

        db = get_session()
        try:
            batch = ops_repo.get_latest_sync_status(db, "fixed_indices")
            incomplete = batch is not None and batch.status == "partial"
        finally:
            db.close()
        if incomplete:
            raise RuntimeError("fixed indices still have missing daily bars")
        _log("kline_init", self.request.id, "success", f"fixed indices presync done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_init_fixed_indices failed")
        _log("kline_init", self.request.id, "failed", str(exc))
        redis.set('provider:fixed-indices-retry', '1', ex=120)
        raise self.retry(exc=exc, countdown=120, max_retries=3)
    finally:
        redis.delete('provider:presync:queued')
        lock_conn.execute(text("SELECT pg_advisory_unlock(4000000001)"))
        lock_conn.close()


@celery_app.task(
    bind=True,
    name="app.worker.tasks.sync_tasks.catalog_sync",
    autoretry_for=(Exception,),
    retry_backoff=3,
    retry_kwargs={"max_retries": 3},
)
def catalog_sync(self) -> dict:
    """全量标的目录同步（每日凌晨 + 启动/手动触发）。外部源异常自动重试 3 次（3s/9s/27s）。"""
    from app.utils.redis_client import get_redis_client

    lock = get_redis_client().lock('provider:catalog:running', timeout=3600)
    if not lock.acquire(blocking=False):
        return {'skipped': 'catalog sync already running'}
    _log("catalog_sync", self.request.id, "running", "start")
    try:
        result = sync_service.run_catalog_sync()
        _log("catalog_sync", self.request.id, "success", f"done: {result}")
        if result.get("status") == "partial":
            # 数量不达标：1 小时后自动补一次
            self.retry(countdown=3600, max_retries=1)
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("catalog_sync failed")
        _log("catalog_sync", self.request.id, "failed", str(exc))
        raise
    finally:
        lock.release()


@celery_app.task(autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def refresh_stockdb_catalog() -> dict:
    result = sync_service.run_catalog_sync(force=True, local_only=True)
    if result["status"] != "done":
        raise RuntimeError("StockDB directory is unavailable")
    return result
