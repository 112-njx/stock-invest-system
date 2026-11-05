"""行情同步服务：K线全量/增量、实时轮询。被 Celery 任务调用，不阻塞主线程。

写入链路：分区K线 upsert → snapshot_realtime → Redis 缓存（快照按 TTL）。
"""

import logging
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.data_providers.base import RealtimeQuote, RealtimeSymbol
from app.data_providers.factory import get_provider
from app.models.symbol import Symbol
from app.models.user import UserWatchlist
from app.repositories import kline_repo, ops_repo, snapshot_repo, symbol_repo, user_repo
from app.utils import market_cache
from app.utils.db import get_session
from app.utils.kline_partition import ensure_current_partitions

logger = logging.getLogger(__name__)
settings = get_settings()
ALL_PERIODS = ("1d", "15m")


def is_market_open(now: datetime | None = None) -> bool:
    """A股交易时段判断（本地时区 工作日 9:30-11:30 / 13:00-15:00）。"""
    now = now or datetime.now(settings.tz)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return (930 <= hm <= 1130) or (1300 <= hm <= 1500)


def _provider_params(sym: Symbol) -> tuple[str, str]:
    """返回 (provider symbol 参数, asset_type)。行业指数（code 空/BK/881 开头）用名称走行业板块。

    BKxxxx=东财板块代码、881xxx=同花顺行业代码（东财被限流时由 THS resolve_index_code 兜底回填）。
    """
    if sym.type == "index":
        if not sym.code or sym.code.startswith(("BK", "881")):
            return sym.name, "industry_index"
        return sym.code, "index"
    return sym.code, sym.type


def _write_bars(db, period: str, symbol_id: int, bars) -> int:
    """幂等写 K 线 + 失效缓存 + 推送最新末根（WS 增量）。"""
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
        if previous_latest is None or market_cache.as_utc(newest.ts) >= market_cache.as_utc(previous_latest):
            from app.ws import publisher

            publisher.publish_kline(symbol_id, period, market_cache.kline_bar_to_dict(newest))
    return added


def _sync_symbol_klines(db, provider, sym: Symbol, start: datetime, end: datetime,
                        watched_a_share: bool) -> dict[str, int]:
    symbol_param, asset_type = _provider_params(sym)
    counts = {}
    for period in ALL_PERIODS:
        fetch = provider.fetch_kline_all if watched_a_share and period == "1d" else provider.fetch_kline
        bars = fetch(symbol_param, period, start, end, asset_type)
        if period == "1d" and not bars:
            raise RuntimeError(f"{sym.name} 的所有数据源均未返回日 K")
        counts[period] = _write_bars(db, period, sym.id, bars)
    return counts


def _mark_watchlist_synced(db, symbol_id: int, status: str) -> None:
    """同步结果回写关注列表 sync_status（best-effort，不影响主链路）。"""
    try:
        user_repo.update_watchlist_sync_status(db, symbol_id, status)
    except Exception:  # noqa: BLE001
        logger.warning("watchlist sync status update failed: symbol_id=%s", symbol_id, exc_info=True)


# ---- V0.2 1.1 启动预同步 / 缓存预热 ----
def stale_fixed_index_count(db) -> tuple[int, int]:
    symbols = symbol_repo.list_fixed_indices(db)
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
        symbols = symbol_repo.list_fixed_indices(db)
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
    """固定指数最近500根日K + 最新快照写 Redis（best-effort，失败不阻断启动）。"""
    db = get_session()
    try:
        symbols = symbol_repo.list_fixed_indices(db)
        kline_warmed, snap_warmed = 0, 0
        for sym in symbols:
            bars = kline_repo.latest_bars(db, "1d", sym.id, 500)
            if bars:
                market_cache.set_kline_cache(sym.id, "1d", 500, [market_cache.kline_bar_to_dict(b) for b in bars])
                kline_warmed += 1
            snap = snapshot_repo.get_snapshot(db, sym.id)
            if snap:
                market_cache.set_snapshot_cache(sym.id, market_cache.snapshot_to_cache_dict(snap))
                snap_warmed += 1
        return {"kline_warmed": kline_warmed, "snapshot_warmed": snap_warmed, "total": len(symbols)}
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
            if sym is None:
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


# ---- 实时快照 ----
def run_realtime_poll(symbol_id: int | None = None) -> dict:
    """实时快照轮询：拉取 → 特殊字段补全（行业K线推导/指数PE/市值/溢价） → 写快照与特殊表 → Redis 缓存。"""
    db = get_session()
    try:
        provider = get_provider()
        symbols: list[Symbol] = [db.get(Symbol, symbol_id)] if symbol_id else symbol_repo.list_realtime_symbols(db)
        symbols = [s for s in symbols if s is not None]
        if not symbols:
            return {"synced": 0}
        ops_repo.upsert_sync_task(db, "realtime", symbol_id, "running", datetime.now(UTC))
        req = [RealtimeSymbol(code=sym.code, name=sym.name, asset_type=_provider_params(sym)[1]) for sym in symbols]
        quotes = provider.fetch_realtime(req)

        index_pe = {}

        synced = 0
        for sym, quote in zip(symbols, quotes, strict=True):
            if not quote.available or quote.price is None:
                # 实时源全部不可用 → K线推导兜底快照（updated_at 为K线时间，页面据 data_age_seconds 标注而非显示 '--'）
                derived = derive_snapshot_from_kline(db, sym)
                if derived is None:
                    continue
                quote = derived
            atype = _provider_params(sym)[1]
            quote.extra["symbol_id"] = sym.id
            if atype == "industry_index":
                _fill_industry_quote_from_kline(db, sym, quote)
            elif atype == "index":
                quote.extra["pe"] = index_pe.get(sym.name)
            snapshot_repo.upsert_snapshot(db, quote)
            _cache_snapshot(sym.id, quote)
            from app.ws import publisher

            publisher.publish_snapshot(sym.id, market_cache.snapshot_to_cache_dict(quote))
            # 特殊字段表：个股总市值/PE、ETF净值/溢价、指数PE（best-effort，任一字段非 None 才写避免覆盖旧值）
            if atype == "stock" and (quote.extra.get("market_cap") is not None or quote.extra.get("pe") is not None):
                snapshot_repo.upsert_fundamentals(db, sym.id, quote.extra.get("market_cap"), quote.extra.get("pe"))
            elif atype == "etf" and (quote.extra.get("nav") is not None or quote.extra.get("premium") is not None):
                snapshot_repo.upsert_etf_premium(db, sym.id, quote.extra.get("nav"), quote.extra.get("premium"))
            elif atype == "index" and quote.extra.get("pe") is not None:
                snapshot_repo.upsert_index_valuation(db, sym.id, quote.extra.get("pe"))
            synced += 1
        ops_repo.upsert_sync_task(
            db,
            "realtime",
            symbol_id,
            "success",
            datetime.now(UTC),
            next_run_at=datetime.now(UTC) + timedelta(seconds=settings.REALTIME_POLL_INTERVAL),
        )
        db.commit()
        return {"synced": synced}
    finally:
        db.close()


def _fill_industry_quote_from_kline(db, sym: Symbol, quote) -> None:
    """行业指数基本数据补全：板块实时接口仅最新价/涨跌额/涨跌幅/换手率，缺昨收/今开/高低/量/额/振幅，用日K推导。

    昨收=前一根日K close，今开/最高/最低/量/额=最新根对应值，振幅=(high-low)/pre_close×100。
    """
    try:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)
        bars = kline_repo.get_bars(db, "1d", sym.id, start, end, limit=2)
        if not bars:
            return
        latest = bars[-1]
        prev = bars[-2] if len(bars) >= 2 else None
        if quote.open is None:
            quote.open = float(latest.open)
        if quote.high is None:
            quote.high = float(latest.high)
        if quote.low is None:
            quote.low = float(latest.low)
        if quote.volume is None:
            quote.volume = int(latest.volume)
        if quote.amount is None:
            quote.amount = float(latest.amount)
        if quote.pre_close is None:
            quote.pre_close = float(prev.close) if prev else float(latest.close)
        if quote.amplitude is None and quote.high and quote.low and quote.pre_close:
            quote.amplitude = (quote.high - quote.low) / quote.pre_close * 100 if quote.pre_close else None
    except Exception:  # noqa: BLE001 K线推导失败不影响该行其余字段
        logger.warning("industry kline fill failed: symbol_id=%s", sym.id, exc_info=True)


def derive_snapshot_from_kline(db, sym: Symbol) -> RealtimeQuote | None:
    """实时源全部不可用时，用最新日K收盘价推导全字段快照（updated_at=K线时间，前端据 data_age_seconds 标注）。

    price=最新日K close，change/change_pct=与前一 close 差，OHLC/量/额取最新根，振幅=(high-low)/pre_close。
    返回 None 表示无K线可推导（诚实留空），不硬造快照。
    """
    try:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)
        bars = kline_repo.get_bars(db, "1d", sym.id, start, end, limit=2)
        if not bars:
            return None
        latest = bars[-1]
        prev = bars[-2] if len(bars) >= 2 else None
        pre_close = float(prev.close) if prev else float(latest.close)
        change = float(latest.close) - pre_close
        change_pct = (change / pre_close * 100) if pre_close else None
        amplitude = (
            (float(latest.high) - float(latest.low)) / pre_close * 100
            if pre_close and latest.high is not None and latest.low is not None
            else None
        )
        return RealtimeQuote(
            code=sym.code,
            name=sym.name,
            asset_type=_provider_params(sym)[1],
            price=float(latest.close),
            change=change,
            change_pct=change_pct,
            open=float(latest.open),
            high=float(latest.high),
            low=float(latest.low),
            pre_close=pre_close,
            volume=int(latest.volume) if latest.volume is not None else None,
            amount=float(latest.amount) if latest.amount is not None else None,
            turnover=None,
            amplitude=amplitude,
            updated_at=latest.ts,
            available=True,
        )
    except Exception:  # noqa: BLE001 K线推导失败不影响主链路
        logger.warning("derive snapshot from kline failed: symbol_id=%s", sym.id, exc_info=True)
        return None


def _cache_snapshot(symbol_id: int, quote) -> None:
    """快照写 Redis（完整 14 项字段，TTL 走配置），供行情 API 快速返回。"""
    market_cache.set_snapshot_cache(symbol_id, market_cache.snapshot_to_cache_dict(quote))
