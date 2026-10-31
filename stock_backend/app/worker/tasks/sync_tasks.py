"""行情同步 Celery 任务：kline_init / kline_incremental / realtime_poll。

任务内只做薄编排：调用同步服务，状态与全链路日志写 sync_tasks / task_logs。
"""

import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.request_id import get_request_id
from app.models.user import UserWatchlist
from app.services import sync_service
from app.utils.db import get_session
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


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.watchlist_stock_sync")
def watchlist_stock_sync(self, symbol_id: int, initialize: bool = False) -> dict:
    """关注 A 股的首次初始化或日 K 增量与缺口修复。"""
    from app.repositories import kline_repo, ops_repo, user_repo
    from app.services import kline_quality_service
    from app.utils import market_cache

    task_type = "kline_init" if initialize else "kline_incremental"
    _log(task_type, self.request.id, "running", f"watchlist symbol_id={symbol_id}")
    db = get_session()
    try:
        if initialize:
            result = sync_service.run_kline_init(symbol_id=symbol_id)
        else:
            result = sync_service.run_kline_incremental(symbol_id=symbol_id)
        latest = kline_repo.latest_ts(db, "1d", symbol_id)
        expected = kline_quality_service.last_completed_mainland_day(db)
        if latest is None or expected is None or latest.astimezone(kline_quality_service.settings.tz).date() < expected:
            raise RuntimeError(f"关注股票最新日 K 未更新到已完成交易日 {expected}")
        quality = kline_quality_service.get_quality(db, symbol_id, "1d")
        if quality is None or quality.status != "complete":
            raise RuntimeError(f"关注股票历史日 K 仍有缺口：{quality.missing_count if quality else '未核验'}")
        user_repo.update_watchlist_sync_status(db, symbol_id, "done")
        db.commit()
        _log(task_type, self.request.id, "success", f"watchlist symbol_id={symbol_id}: {result}")
        return result
    except Exception as exc:
        db.rollback()
        ops_repo.upsert_sync_task(db, task_type, symbol_id, "failed", datetime.now(UTC))
        user_repo.update_watchlist_sync_status(db, symbol_id, "failed")
        db.commit()
        _log(task_type, self.request.id, "failed", str(exc))
        raise
    finally:
        for user_id in db.scalars(select(UserWatchlist.user_id).where(UserWatchlist.symbol_id == symbol_id)):
            market_cache.invalidate_watchlist_cache(user_id)
        db.close()


@celery_app.task(name="app.worker.tasks.sync_tasks.kline_backfill")
def kline_backfill(symbol_id: int, period: str, start_iso: str, end_iso: str) -> dict:
    """按用户请求的历史窗口补取，结果供前端轮询。"""
    from datetime import datetime

    from app.data_providers.factory import get_provider
    from app.models.symbol import Symbol
    from app.services.sync_service import _provider_params, _write_bars

    db = get_session()
    try:
        sym = db.get(Symbol, symbol_id)
        if sym is None:
            return {"fetched": 0, "added": 0}
        symbol_param, asset_type = _provider_params(sym)
        source_period = "1d" if period == "1w" else period
        bars, confirmed_empty = get_provider().fetch_kline_checked(
            symbol_param, source_period, datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso), asset_type
        )
        added = _write_bars(db, source_period, symbol_id, bars)
        db.commit()
        return {"fetched": len(bars), "added": added, "confirmed_empty": confirmed_empty if not bars else False}
    finally:
        db.close()


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_init_fixed_indices")
def kline_init_fixed_indices(self) -> dict:
    """固定指数预同步：同步当前固定大盘/行业指数，进度写 sync_status。"""
    from app.utils.redis_client import get_redis_client

    redis = get_redis_client()
    lock = redis.lock('provider:presync:running', timeout=7200)
    if not lock.acquire(blocking=False):
        return {'skipped': 'fixed indices sync already running'}
    _log("kline_init", self.request.id, "running", "fixed indices presync start")
    try:
        result = sync_service.run_fixed_indices_sync()
        _log("kline_init", self.request.id, "success", f"fixed indices presync done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_init_fixed_indices failed")
        _log("kline_init", self.request.id, "failed", str(exc))
        raise
    finally:
        redis.delete('provider:presync:queued')
        lock.release()


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.kline_incremental")
def kline_incremental(self, symbol_id: int | None = None) -> dict:
    """每日收盘后增量同步。"""
    _log("kline_incremental", self.request.id, "running", f"start symbol_id={symbol_id}")
    try:
        result = sync_service.run_kline_incremental(symbol_id=symbol_id)
        _log("kline_incremental", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("kline_incremental failed")
        _log("kline_incremental", self.request.id, "failed", str(exc))
        raise


@celery_app.task(bind=True, name="app.worker.tasks.sync_tasks.realtime_poll")
def realtime_poll(self, symbol_id: int | None = None, force: bool = False) -> dict:
    """交易时段实时快照轮询；非交易时段跳过（beat 周期触发，force 用于手动验证/运维）。"""
    if not force and not sync_service.is_market_open():
        return {"skipped": "market closed"}
    _log("realtime", self.request.id, "running", f"start symbol_id={symbol_id}")
    try:
        result = sync_service.run_realtime_poll(symbol_id=symbol_id)
        _log("realtime", self.request.id, "success", f"done: {result}")
        return result
    except Exception as exc:  # noqa: BLE001
        logger.exception("realtime_poll failed")
        _log("realtime", self.request.id, "failed", str(exc))
        raise


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


@celery_app.task(name="app.worker.tasks.sync_tasks.provider_probe")
def provider_probe() -> dict:
    """探测熔断中的行情 Provider（固定标的 1 根日K），成功即自动恢复。"""
    from app.data_providers.factory import get_provider

    try:
        results = get_provider().probe()
        if results:
            logger.info("[provider] probe results: %s", results)
        return {"probed": results}
    except Exception as exc:  # noqa: BLE001
        logger.warning("provider_probe failed: %s", exc)
        return {"probed": [], "error": str(exc)[:120]}
