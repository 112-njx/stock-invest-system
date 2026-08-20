"""行情同步服务：K线全量/增量、实时轮询。被 Celery 任务调用，不阻塞主线程。

写入链路：分区K线 upsert → snapshot_realtime → Redis 缓存（快照按 TTL）。
"""

import logging
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.data_providers.base import RealtimeSymbol
from app.data_providers.factory import get_provider
from app.models.kline import KLINE_MODELS
from app.models.symbol import Symbol
from app.repositories import kline_repo, ops_repo, snapshot_repo, symbol_repo, user_repo
from app.utils import market_cache
from app.utils.db import get_session
from app.utils.kline_partition import ensure_current_partitions

logger = logging.getLogger(__name__)
settings = get_settings()
ALL_PERIODS = tuple(KLINE_MODELS.keys())


def is_market_open(now: datetime | None = None) -> bool:
    """A股交易时段判断（本地时区 工作日 9:30-11:30 / 13:00-15:00）。"""
    now = now or datetime.now(settings.tz)
    if now.weekday() >= 5:
        return False
    hm = now.hour * 100 + now.minute
    return (930 <= hm <= 1130) or (1300 <= hm <= 1500)


def _provider_params(sym: Symbol) -> tuple[str, str]:
    """返回 (provider symbol 参数, asset_type)。行业指数（code 空/BK开头）用名称走行业板块。"""
    if sym.type == "index":
        if not sym.code or sym.code.startswith("BK"):
            return sym.name, "industry_index"
        return sym.code, "index"
    return sym.code, sym.type


def _write_bars(db, period: str, symbol_id: int, bars) -> int:
    """幂等写 K 线 + 失效缓存 + 推送最新末根（WS 增量）。"""
    added = kline_repo.upsert_bars(db, period, symbol_id, bars)
    if added:
        market_cache.invalidate_kline_cache(symbol_id, period)
        if bars:
            from app.ws import publisher

            publisher.publish_kline(symbol_id, period, market_cache.kline_bar_to_dict(bars[-1]))
    return added


def _mark_watchlist_synced(db, symbol_id: int, status: str) -> None:
    """同步结果回写关注列表 sync_status（best-effort，不影响主链路）。"""
    try:
        user_repo.update_watchlist_sync_status(db, symbol_id, status)
    except Exception:  # noqa: BLE001
        logger.warning("watchlist sync status update failed: symbol_id=%s", symbol_id, exc_info=True)


# ---- V0.2 1.1 启动预同步 / 缓存预热 ----
def stale_fixed_index_count(db) -> tuple[int, int]:
    """固定指数最新日K超过1天或无数据的数量，返回 (stale, total)。"""
    symbols = symbol_repo.list_fixed_indices(db)
    threshold = datetime.now(UTC) - timedelta(days=1)
    stale = 0
    for sym in symbols:
        ts = market_cache.as_utc(kline_repo.latest_ts(db, "1d", sym.id))  # DB naive → UTC
        if ts is None or ts < threshold:
            stale += 1
    return stale, len(symbols)


def maybe_presync_fixed_indices() -> dict:
    """检查固定指数K线新鲜度，过期则触发 kline_init_fixed_indices 任务（不阻塞 API 启动）。"""
    db = get_session()
    try:
        stale, total = stale_fixed_index_count(db)
        if stale == 0:
            return {"triggered": False, "stale": 0, "total": total}
        from app.worker.tasks.sync_tasks import kline_init_fixed_indices

        task = kline_init_fixed_indices.delay()
        ops_repo.upsert_sync_status(
            db,
            "fixed_indices",
            "queued",
            0,
            total,
            f"检测到 {stale}/{total} 个固定指数无/过期数据，已触发预同步",
            started_at=datetime.now(UTC),
        )
        db.commit()
        logger.info("fixed indices presync triggered: task=%s stale=%d/%d", task.id, stale, total)
        return {"triggered": True, "task_id": task.id, "stale": stale, "total": total}
    finally:
        db.close()


def run_fixed_indices_sync() -> dict:
    """固定指数预同步：49 条固定大盘/行业指数全周期K线，进度写 sync_status（X/49）。"""
    db = get_session()
    try:
        provider = get_provider()
        symbols = symbol_repo.list_fixed_indices(db)
        total = len(symbols)
        if total == 0:
            return {"synced": 0}
        end = datetime.now(UTC)
        start = end - timedelta(days=settings.KLINE_INIT_DAYS)
        ensure_current_partitions(db)
        ops_repo.upsert_sync_status(
            db, "fixed_indices", "running", 0, total, "固定指数预同步开始", started_at=datetime.now(UTC)
        )
        db.commit()
        results: dict = {}
        for i, sym in enumerate(symbols, 1):
            if sym.type == "index" and not sym.code:  # 行业指数 code 回填
                code = provider.resolve_index_code(sym.name)
                if code:
                    symbol_repo.update_code(db, sym.id, code)
            counts: dict = {}
            for period in ALL_PERIODS:
                symbol_param, asset_type = _provider_params(sym)
                bars = provider.fetch_kline(symbol_param, period, start, end, asset_type)
                counts[period] = _write_bars(db, period, sym.id, bars)
            ops_repo.upsert_sync_task(db, "kline_init", sym.id, "success", datetime.now(UTC))
            _mark_watchlist_synced(db, sym.id, "done")
            progress = int(i / total * 100)
            ops_repo.upsert_sync_status(
                db, "fixed_indices", "running", progress, total, f"已同步 {i}/{total}"
            )
            db.commit()
            results[sym.code or sym.name] = counts
        ops_repo.upsert_sync_status(
            db, "fixed_indices", "done", 100, total, "固定指数预同步完成", finished_at=datetime.now(UTC)
        )
        db.commit()
        return results
    finally:
        db.close()


# ---- V0.2 3.1 全量标的目录预同步 ----
def run_catalog_sync() -> dict:
    """全A股 + ETF 目录预同步：akshare 拉取 → 幂等 upsert symbols（is_catalog=True）。

    数量校验：A股≥4800、ETF≥500，不达标返回 partial（调用方调度 1h 后重试）。
    """
    db = get_session()
    try:
        provider = get_provider()
        ops_repo.upsert_sync_status(db, "catalog", "running", 0, 0, "全量目录同步开始", started_at=datetime.now(UTC))
        catalog = provider.fetch_catalog()
        stocks, etfs = catalog.get("stocks") or [], catalog.get("etfs") or []
        added_stocks = symbol_repo.upsert_catalog_symbols(db, [(c, n, "stock", "SSE") for c, n in stocks])
        added_etfs = symbol_repo.upsert_catalog_symbols(db, [(c, n, "etf", "SSE") for c, n in etfs])
        db.commit()
        # 搜索缓存失效：目录已更新
        market_cache.invalidate_search_cache()
        stock_count = symbol_repo.count_type(db, "stock")
        etf_count = symbol_repo.count_type(db, "etf")
        partial = stock_count < 4800 or etf_count < 500
        status = "partial" if partial else "done"
        message = (
            f"A股 {stock_count} 只 / ETF {etf_count} 只，本次新增 stock={added_stocks} etf={added_etfs}"
            + ("，未达标待 1h 后重试" if partial else "")
        )
        ops_repo.upsert_sync_status(
            db, "catalog", status, 100, stock_count + etf_count, message, finished_at=datetime.now(UTC)
        )
        db.commit()
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
    """启动检查：目录内 A 股 <4000 则触发 catalog_sync 任务（不阻塞启动）。"""
    db = get_session()
    try:
        count = symbol_repo.count_catalog_stocks(db)
        if count >= 4000:
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
                market_cache.set_kline_cache(
                    sym.id, "1d", 500, [market_cache.kline_bar_to_dict(b) for b in bars]
                )
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
def run_kline_init(symbol_id: int | None = None, days: int | None = None) -> dict:
    """首次全量历史K线：全标的多周期拉取并幂等入库；行业指数同步回填 code。"""
    db = get_session()
    try:
        provider = get_provider()
        days = days or settings.KLINE_INIT_DAYS
        end = datetime.now(UTC)
        start = end - timedelta(days=days)
        ensure_current_partitions(db)
        symbols: list[Symbol] = [db.get(Symbol, symbol_id)] if symbol_id else symbol_repo.list_kline_sync_symbols(db)
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
            counts: dict = {}
            for period in ALL_PERIODS:
                symbol_param, asset_type = _provider_params(sym)
                bars = provider.fetch_kline(symbol_param, period, start, end, asset_type)
                added = _write_bars(db, period, sym.id, bars)
                counts[period] = added
                logger.info("kline_init %s %s added=%d", sym.name, period, added)
            ops_repo.upsert_sync_task(db, "kline_init", sym.id, "success", datetime.now(UTC))
            _mark_watchlist_synced(db, sym.id, "done")
            db.commit()
            results[sym.code or sym.name] = counts
        return results
    finally:
        db.close()


def run_kline_incremental(symbol_id: int | None = None, back_days: int = 10) -> dict:
    """每日收盘后增量：近 back_days 天多周期K线拉取并幂等入库。"""
    db = get_session()
    try:
        provider = get_provider()
        end = datetime.now(UTC)
        start = end - timedelta(days=back_days)
        ensure_current_partitions(db)
        symbols: list[Symbol] = [db.get(Symbol, symbol_id)] if symbol_id else symbol_repo.list_kline_sync_symbols(db)
        results: dict = {}
        for sym in symbols:
            if sym is None:
                continue
            ops_repo.upsert_sync_task(db, "kline_incremental", sym.id, "running", datetime.now(UTC))
            counts: dict = {}
            for period in ALL_PERIODS:
                symbol_param, asset_type = _provider_params(sym)
                bars = provider.fetch_kline(symbol_param, period, start, end, asset_type)
                added = _write_bars(db, period, sym.id, bars)
                counts[period] = added
            ops_repo.upsert_sync_task(db, "kline_incremental", sym.id, "success", datetime.now(UTC))
            db.commit()
            results[sym.code or sym.name] = counts
        return results
    finally:
        db.close()


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

        # 指数 PE：乐咕 best-effort（仅覆盖可取 A 股指数，其余 None 留空），失败不阻塞主链路
        index_names = [
            sym.name for sym, q in zip(symbols, quotes, strict=True) if _provider_params(sym)[1] == "index" and q.available
        ]
        index_pe: dict[str, float | None] = {}
        if index_names:
            try:
                index_pe = provider.fetch_index_pe(index_names) or {}
            except Exception:  # noqa: BLE001
                logger.warning("fetch_index_pe failed, skip index PE this round")

        synced = 0
        for sym, quote in zip(symbols, quotes, strict=True):
            if not quote.available or quote.price is None:
                continue
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
            if atype == "stock" and (
                quote.extra.get("market_cap") is not None or quote.extra.get("pe") is not None
            ):
                snapshot_repo.upsert_fundamentals(db, sym.id, quote.extra.get("market_cap"), quote.extra.get("pe"))
            elif atype == "etf" and (
                quote.extra.get("nav") is not None or quote.extra.get("premium") is not None
            ):
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


def _cache_snapshot(symbol_id: int, quote) -> None:
    """快照写 Redis（完整 14 项字段，TTL 走配置），供行情 API 快速返回。"""
    market_cache.set_snapshot_cache(symbol_id, market_cache.snapshot_to_cache_dict(quote))
