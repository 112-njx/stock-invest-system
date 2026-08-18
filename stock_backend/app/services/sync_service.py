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
from app.repositories import kline_repo, ops_repo, snapshot_repo, symbol_repo
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
                added = kline_repo.upsert_bars(db, period, sym.id, bars)
                counts[period] = added
                logger.info("kline_init %s %s added=%d", sym.name, period, added)
            ops_repo.upsert_sync_task(db, "kline_init", sym.id, "success", datetime.now(UTC))
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
                added = kline_repo.upsert_bars(db, period, sym.id, bars)
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
            _cache_snapshot(sym.id, quote)
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
    """快照写 Redis（TTL 走配置），供行情 API 快速返回。"""
    try:
        import json

        from app.utils.redis_client import get_redis_client

        key = f"snapshot:{symbol_id}"
        get_redis_client().set(
            key,
            json.dumps({"price": quote.price, "updated_at": quote.updated_at and quote.updated_at.isoformat()}),
            ex=settings.SNAPSHOT_CACHE_TTL,
        )
    except Exception:  # noqa: BLE001 Redis 不可用不影响主链路
        logger.warning("snapshot redis cache failed: symbol_id=%s", symbol_id)
