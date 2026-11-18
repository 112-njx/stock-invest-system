"""Index history synchronization, security catalog and cache preparation."""

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
    if bars and bars[0].source == 'akshare':
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


def prepare_history_window(db, sym, period, start, end, *, initial=False):
    """Prepare a worker window atomically, refreshing the complete stored qfq range."""
    from sqlalchemy import func, select, text
    from app.models.kline import KLINE_MODELS
    from app.services import local_history, source_history

    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 5000000000 + sym.id})
    if period in {'1m', '5m', '30m', '60m'} and sym.type != 'stock':
        raise ValueError('新增分钟周期仅支持个股')
    model = KLINE_MODELS[period]
    if sym.type in {"stock", "etf"}:
        bars = local_history.read(sym, period, None if initial else start, end)
        if not bars and not initial:
            # The requested historical interval may be outside the local coverage.
            bars = source_history.window(db, sym.id, period, start, end)
        if not bars:
            cached = source_history.load(db, sym.id, period)
            bars = [bar for bar in cached if (initial or start <= bar.ts) and bar.ts <= end]
        return {"fetched": len(bars), "added": 0, "confirmed_empty": not bars}

    first, last = db.execute(select(func.min(model.ts), func.max(model.ts)).where(
        model.symbol_id == sym.id, model.source == "stockdb")).one()
    start = min(start, market_cache.as_utc(first)) if first is not None else start
    end = max(end, market_cache.as_utc(last)) if last is not None else end
    code, asset = _provider_params(sym)
    provider = get_provider()
    bars, confirmed = provider.fetch_kline_checked(code, period, start, end, asset)
    if not bars and initial:
        # A recent empty window does not imply that a suspended/delisted security
        # has no older history. Only initial chart loading expands this far.
        bars, confirmed = provider.fetch_kline_checked(code, period, source_history.FIRST, end, asset)
    if not bars and not confirmed:
        raise RuntimeError('历史行情源不可用，请检查本地行情服务')
    added = _write_bars(db, period, sym.id, bars)
    db.commit()
    if bars:
        # A query may have cached an empty/old series before this transaction committed.
        from app.services.indicator_service import invalidate_indicator_cache
        from app.ws.publisher import publish_kline_refresh
        market_cache.invalidate_kline_cache(sym.id, period)
        invalidate_indicator_cache(sym.id, period)
        publish_kline_refresh(sym.id, period)
    return {'fetched': len(bars), 'added': added, 'confirmed_empty': confirmed if not bars else False}


def _sync_symbol_klines(db, provider, sym: Symbol, start: datetime, end: datetime) -> dict[str, int]:
    code, asset = _provider_params(sym)
    bars_by_period = {period: provider.fetch_kline(code, period, start, end, asset) for period in ALL_PERIODS}
    required = ("1d", "1w", "1mon") if asset == "sw_index" else ("1d",)
    for period in required:
        if not bars_by_period[period]:
            raise RuntimeError(f"{sym.name} 的 {period} K 线未返回")
    return {period: _write_bars(db, period, sym.id, bars) for period, bars in bars_by_period.items()}


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
def run_catalog_sync(force: bool = False, *, local_only: bool = False) -> dict:
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
        if local_only:
            from app.data_providers.stockdb import StockDBProvider
            provider = StockDBProvider()
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
    """同步固定指数历史，必要时补齐行业代码。"""
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
            if sym is None or sym.type in {"stock", "etf"} or not supported_symbol(sym):
                continue
            ops_repo.upsert_sync_task(db, "kline_init", sym.id, "running", datetime.now(UTC))
            if sym.type == "index" and not sym.code:  # 行业指数 code 回填
                code = provider.resolve_index_code(sym.name)
                if code:
                    symbol_repo.update_code(db, sym.id, code)
                    logger.info("backfill industry index code: %s -> %s", sym.name, code)
            from sqlalchemy import func, text
            from app.models.kline import KLINE_MODELS

            db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": 5000000000 + sym.id})
            oldest = [db.scalar(select(func.min(model.ts)).where(model.symbol_id == sym.id))
                      for model in KLINE_MODELS.values()]
            stored = [market_cache.as_utc(ts) for ts in oldest if ts is not None]
            symbol_start = min([start, *stored])
            counts = _sync_symbol_klines(db, provider, sym, symbol_start, end)
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
