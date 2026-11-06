"""行情同步服务：K线全量/增量、缓存准备。被 Celery 任务调用，不阻塞主线程。

写入链路：StockDB K线入库；AkShare历史按独立开关入库或仅缓存。
"""

import logging
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.data_providers.factory import get_provider
from app.models.symbol import Symbol
from app.models.user import UserWatchlist
from app.repositories import kline_repo, ops_repo, symbol_repo, user_repo
from app.utils import market_cache
from app.utils.db import get_session
from app.utils.kline_partition import ensure_current_partitions

logger = logging.getLogger(__name__)
settings = get_settings()
ALL_PERIODS = ("1d", "15m", "1w", "1mon")


def _provider_params(sym: Symbol) -> tuple[str, str]:
    """返回 (provider symbol 参数, asset_type)。行业指数（code 空/BK/881 开头）用名称走行业板块。

    BKxxxx=东财板块代码、881xxx=同花顺行业代码（东财被限流时由 THS resolve_index_code 兜底回填）。
    """
    if sym.market == "SW":
        return sym.code, "sw_index"
    if sym.type == "index":
        if not sym.code or sym.code.startswith(("BK", "881")):
            return sym.name, "industry_index"
        return sym.code, "index"
    return sym.code, sym.type


def _write_bars(db, period: str, symbol_id: int, bars) -> int:
    """幂等写 K 线 + 失效缓存 + 推送最新末根（WS 增量）。"""
    from app.services.market_policy import history_storage_enabled
    if bars and bars[0].source == 'akshare' and not history_storage_enabled():
        from app.services import source_history
        if not source_history.load(db, symbol_id, period, refresh=True):
            raise RuntimeError('AkShare 历史缓存未准备完成')
        market_cache.invalidate_kline_cache(symbol_id, period)
        from app.services.indicator_service import invalidate_indicator_cache
        from app.ws.publisher import publish_kline_refresh
        invalidate_indicator_cache(symbol_id, period)
        publish_kline_refresh(symbol_id, period)
        return 0
    previous_latest = kline_repo.latest_ts(db, period, symbol_id) if bars else None
    added = kline_repo.upsert_bars(db, period, symbol_id, bars)
    if added:
        market_cache.invalidate_kline_cache(symbol_id, period)
        from app.services.indicator_service import invalidate_indicator_cache

        invalidate_indicator_cache(symbol_id, period)
        if period == "1d":
            invalidate_indicator_cache(symbol_id, "1w")
            invalidate_indicator_cache(symbol_id, "1mon")
        newest = max(bars, key=lambda b: b.ts)
        selected = kline_repo.latest_bars(db, period, symbol_id, limit=1)
        if selected and selected[0].source == newest.source and (
            previous_latest is None or market_cache.as_utc(newest.ts) >= market_cache.as_utc(previous_latest)
        ):
            from app.ws import publisher

            publisher.publish_kline(symbol_id, period, market_cache.kline_bar_to_dict(newest))
    return added


def _sync_symbol_klines(db, provider, sym: Symbol, start: datetime, end: datetime,
                        watched_a_share: bool) -> dict[str, int]:
    symbol_param, asset_type = _provider_params(sym)
    fetched = {}
    for period in ALL_PERIODS:
        fetch = provider.fetch_kline_all if watched_a_share and period == "1d" else provider.fetch_kline
        bars = fetch(symbol_param, period, start, end, asset_type)
        if period == "1d" and not bars:
            raise RuntimeError(f"{sym.name} 的所有数据源均未返回日 K")
        if asset_type in {'stock', 'etf', 'sw_index'} and period in {'1w', '1mon'} and not bars:
            raise RuntimeError(f'{sym.name} 的 {period} 数据获取失败，未完成同步，请检查数据源后重试')
        from app.services.market_policy import history_storage_enabled
        if asset_type in {"stock", "etf"} and not (bars and bars[0].source == 'akshare' and not history_storage_enabled()):
            from sqlalchemy import func, select
            from app.models.kline import KLINE_MODELS

            model = KLINE_MODELS[period]
            first, last = db.execute(select(func.min(model.ts), func.max(model.ts)).where(
                model.symbol_id == sym.id, model.source == (bars[0].source if bars else "stockdb")
            )).one()
            def boundary(ts):
                stamp = market_cache.as_utc(ts)
                if period == '1w':
                    return (stamp - timedelta(days=stamp.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                if period == '1mon':
                    return stamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                return stamp
            # A qfq refresh must replace the whole stored range in one transaction.
            # A stale local source must never rebase the prefix while leaving a newer tail.
            if first is not None and (not bars or
                    min(boundary(bar.ts) for bar in bars) > boundary(first) or
                    max(boundary(bar.ts) for bar in bars) < boundary(last)):
                logger.warning("qfq coverage_rejected symbol=%s period=%s stored=%s..%s",
                               sym.code, period, first, last)
                raise RuntimeError(
                    f"{sym.name} 的 {period} 数据未覆盖库中已有历史，已阻止覆盖以保护前复权基准；"
                    "请先运行数据更新.exe 更新 Free-StockDB 后重试"
                )
        fetched[period] = bars
    # Validate both periods before publishing or writing either of them.
    return {period: _write_bars(db, period, sym.id, bars) for period, bars in fetched.items()}


def _mark_watchlist_synced(db, symbol_id: int, status: str) -> None:
    """同步结果回写关注列表 sync_status（best-effort，不影响主链路）。"""
    try:
        user_repo.update_watchlist_sync_status(db, symbol_id, status)
    except Exception:  # noqa: BLE001
        logger.warning("watchlist sync status update failed: symbol_id=%s", symbol_id, exc_info=True)


# ---- V0.2 1.1 启动预同步 / 缓存预热 ----
def supported_symbol(sym):
    from app.services.market_policy import akshare_enabled
    return sym.type != "index" or sym.market == "SW" or akshare_enabled()


def stale_fixed_index_count(db) -> tuple[int, int]:
    symbols = [sym for sym in symbol_repo.list_fixed_indices(db) if supported_symbol(sym)]
    missing = sum(kline_repo.latest_ts(db, "1d", sym.id) is None for sym in symbols)
    return missing, len(symbols)


def maybe_presync_fixed_indices() -> dict:
    """检查固定指数K线新鲜度，过期则触发 kline_init_fixed_indices 任务（不阻塞 API 启动）。"""
    db = get_session()
    try:
        stale, total = stale_fixed_index_count(db)
        if stale == 0:
            return {"triggered": False, "stale": 0, "total": total}
        from app.utils.redis_client import get_redis_client

        redis = get_redis_client()
        if not redis.set('provider:presync:queued', '1', nx=True, ex=3600):
            return {"triggered": False, "reason": "already queued", "stale": stale, "total": total}
        from app.worker.tasks.sync_tasks import kline_init_fixed_indices
        try:
            task = kline_init_fixed_indices.delay()
        except Exception:
            redis.delete('provider:presync:queued')
            raise
        ops_repo.upsert_sync_status(
            db,
            "fixed_indices",
            "queued",
            0,
            total,
            f"检测到 {stale} 个指数未初始化，已触发首次同步",
            started_at=datetime.now(UTC),
        )
        db.commit()
        logger.info("fixed indices presync triggered: task=%s stale=%d/%d", task.id, stale, total)
        return {"triggered": True, "task_id": task.id, "stale": stale, "total": total}
    finally:
        db.close()


def run_fixed_indices_sync(skip_existing: bool = True) -> dict:
    """Initialize missing fixed symbols, or explicitly refresh their stored qfq history."""
    db = get_session()
    try:
        symbols = [sym for sym in symbol_repo.list_fixed_indices(db) if supported_symbol(sym)]
        ops_repo.upsert_sync_status(db, "fixed_indices", "running", 0, len(symbols), "固定指数同步开始")
        db.commit()
        result = {}
        for number, sym in enumerate(symbols, 1):
            if skip_existing and kline_repo.latest_ts(db, "1d", sym.id) is not None:
                continue
            try:
                result[str(sym.id)] = run_kline_init(symbol_id=sym.id)
            except Exception as exc:
                result[str(sym.id)] = {"error": str(exc)[:200]}
                logger.warning('fixed index sync failed code=%s: %s', sym.code, exc, exc_info=True)
            ops_repo.upsert_sync_status(db, "fixed_indices", "running", int(number / len(symbols) * 100),
                                        len(symbols), f"已处理 {number}/{len(symbols)}")
            db.commit()
        failed = sum("error" in item for item in result.values())
        ops_repo.upsert_sync_status(db, "fixed_indices", "partial" if failed else "done", 100, len(symbols),
                                    f"固定指数同步结束，失败 {failed} 个", finished_at=datetime.now(UTC))
        db.commit()
        return result
    finally:
        db.close()


# ---- V0.2 3.1 全量标的目录预同步 ----
def run_catalog_sync(force: bool = False) -> dict:
    """Read the trusted local catalog first, falling back to the existing provider chain."""
    db = get_session()
    try:
        from app.utils.redis_client import get_redis_client

        redis = get_redis_client()
        daily_key = f'provider:catalog:done:{datetime.now(settings.tz):%Y%m%d}'
        if not force and redis.exists(daily_key):
            return {'status': 'done', 'skipped': 'already synced today'}
        provider = get_provider()
        ops_repo.upsert_sync_status(db, "catalog", "running", 0, 0, "全量目录同步开始", started_at=datetime.now(UTC))
        catalog = provider.fetch_catalog()
        stocks, etfs = catalog.get("stocks") or [], catalog.get("etfs") or []
        added_stocks = symbol_repo.upsert_catalog_symbols(db, [(c, n, "stock", "SZSE" if c.startswith(("0", "3")) else "BSE" if c.startswith(("4", "8", "9")) else "SSE") for c, n in stocks])
        added_etfs = symbol_repo.upsert_catalog_symbols(db, [(c, n, "etf", "SZSE" if c.startswith("1") else "SSE") for c, n in etfs])
        db.commit()
        # 搜索缓存失效：目录已更新
        market_cache.invalidate_search_cache()
        stock_count = symbol_repo.count_type(db, "stock")
        etf_count = symbol_repo.count_type(db, "etf")
        partial = not stocks and not etfs
        status = "partial" if partial else "done"
        message = f"A股 {stock_count} 只 / ETF {etf_count} 只，本次新增 stock={added_stocks} etf={added_etfs}" + (
            "，数据源未返回目录，待重试" if partial else ""
        )
        ops_repo.upsert_sync_status(
            db, "catalog", status, 100, stock_count + etf_count, message, finished_at=datetime.now(UTC)
        )
        db.commit()
        if status == 'done':
            redis.set(daily_key, '1', ex=172800)
        logger.info("catalog sync: %s", message)
        return {
            "stock_count": stock_count,
            "etf_count": etf_count,
            "added_stocks": added_stocks,
            "added_etfs": added_etfs,
            "status": status,
        }
    finally:
        db.close()


def maybe_catalog_sync() -> dict:
    """首次启动时初始化空目录。"""
    db = get_session()
    try:
        count = symbol_repo.count_catalog_stocks(db)
        if count > 0:
            return {"triggered": False, "count": count}
        from app.worker.tasks.sync_tasks import catalog_sync

        task = catalog_sync.delay()
        logger.info("catalog sync triggered on startup: count=%d task=%s", count, task.id)
        return {"triggered": True, "task_id": task.id, "count": count}
    finally:
        db.close()


def warmup_fixed_indices_cache() -> dict:
    """固定指数最近500根日K 写 Redis（best-effort，失败不阻断启动）。"""
    db = get_session()
    try:
        symbols = [sym for sym in symbol_repo.list_fixed_indices(db) if supported_symbol(sym)]
        kline_warmed = 0
        for sym in symbols:
            bars = kline_repo.latest_bars(db, "1d", sym.id, 500)
            if bars:
                market_cache.set_kline_cache(sym.id, "1d", 500, [market_cache.kline_bar_to_dict(b) for b in bars])
                kline_warmed += 1
        return {"kline_warmed": kline_warmed, "total": len(symbols)}
    except Exception:  # noqa: BLE001 预热失败不阻断启动
        logger.warning("fixed indices cache warmup failed", exc_info=True)
        return {"warmup_error": True}
    finally:
        db.close()


# ---- K线 ----
def run_kline_init(symbol_id: int | None = None, days: int | None = None, end: datetime | None = None) -> dict:
    """首次全量历史K线：全标的多周期拉取并幂等入库；行业指数同步回填 code。"""
    db = get_session()
    try:
        from app.services import kline_quality_service
        provider = get_provider()
        days = days or settings.KLINE_INIT_DAYS
        end = end or datetime.now(UTC)
        start = end - timedelta(days=days)
        ensure_current_partitions(db)
        symbols: list[Symbol] = [db.get(Symbol, symbol_id)] if symbol_id else symbol_repo.list_kline_sync_symbols(db)
        from sqlalchemy import select

        watched_ids = set(db.scalars(select(UserWatchlist.symbol_id).distinct()))
        results: dict = {}
        for sym in symbols:
            if sym is None or not supported_symbol(sym):
                continue
            ops_repo.upsert_sync_task(db, "kline_init", sym.id, "running", datetime.now(UTC))
            if sym.type == "index" and not sym.code:  # 行业指数 code 回填
                code = provider.resolve_index_code(sym.name)
                if code:
                    symbol_repo.update_code(db, sym.id, code)
                    logger.info("backfill industry index code: %s -> %s", sym.name, code)
            watched_a_share = sym.id in watched_ids and kline_quality_service.is_a_share_stock(sym)
            from sqlalchemy import func, text
            from app.models.kline import KLINE_MODELS

            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 5000000000 + sym.id})
            oldest = [db.scalar(select(func.min(model.ts)).where(model.symbol_id == sym.id))
                      for model in KLINE_MODELS.values()]
            stored = [market_cache.as_utc(ts) for ts in oldest if ts is not None]
            symbol_start = min([start, *stored])
            counts = _sync_symbol_klines(db, provider, sym, symbol_start, end, watched_a_share)
            for period, added in counts.items():
                logger.info("kline_init %s %s added=%d", sym.name, period, added)
            quality = kline_quality_service.check_and_repair(db, sym, provider)
            complete = quality["status"] == "complete"
            ops_repo.upsert_sync_task(db, "kline_init", sym.id,
                                      "failed" if sym.id in watched_ids and not complete else "success", datetime.now(UTC))
            if sym.id in watched_ids:
                _mark_watchlist_synced(db, sym.id, "done" if complete else "failed")
            db.commit()
            from app.services.indicator_service import invalidate_indicator_cache
            from app.ws.publisher import publish_kline_refresh

            for user_id in db.scalars(select(UserWatchlist.user_id).where(UserWatchlist.symbol_id == sym.id).distinct()):
                market_cache.invalidate_watchlist_cache(user_id)
            # Readers may have refilled a cache before the import committed.
            for period, changed in counts.items():
                if changed:
                    for affected in (("1d", "1w", "1mon") if period == "1d" else (period,)):
                        market_cache.invalidate_kline_cache(sym.id, affected)
                        invalidate_indicator_cache(sym.id, affected)
                    publish_kline_refresh(sym.id, period)
            results[sym.code or sym.name] = counts
        return results
    finally:
        db.close()


def run_kline_incremental(symbol_id: int | None = None, back_days: int = 10) -> dict:
    """Compatibility entry point for explicitly requested watchlist refreshes."""
    return run_kline_init(symbol_id=symbol_id)
