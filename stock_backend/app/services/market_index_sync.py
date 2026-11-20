"""Public-source updates for the market page's eight headline indices."""

import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from app.data_providers.base import ProviderError
from app.data_providers.factory import DataProviderFactory
from app.repositories import market_index_repo as repo
from app.utils.db import get_session
from app.utils.market_cache import as_utc

logger = logging.getLogger(__name__)
FIRST = datetime(1990, 1, 1, tzinfo=UTC)
INITIAL_DAYS = {"15m": 90}
OVERLAP = {"1d": 7, "15m": 3, "1w": 14, "1mon": 62}


@lru_cache(maxsize=1)
def _public_provider():
    # Separate circuit breakers from the optional AkShare fallback for equities.
    return DataProviderFactory("eastmoney,sina")


def refresh_period(db, symbol, period, start=None, end=None, *, initial=False):
    if not repo.handles(symbol) or period not in repo.PERIODS:
        raise ValueError("不在行情页大盘指数同步范围内")
    end = as_utc(end) if end else datetime.now(UTC)
    if start is None or initial:
        _, last = repo.coverage(db, symbol.id, period)
        full_start = end - timedelta(days=INITIAL_DAYS[period]) if period in INITIAL_DAYS else FIRST
        start = as_utc(last) - timedelta(days=OVERLAP[period]) if last and start is None else full_start
    start = as_utc(start)
    if start > end:
        return {"fetched": 0, "added": 0, "confirmed_empty": True}
    bars, confirmed = _public_provider().fetch_kline_checked(
        symbol.code, period, start, end, "index", public_index=True,
    )
    if not bars and not confirmed:
        raise ProviderError(f"{symbol.name} {period} 公开数据源不可用")
    rows = [
        dict(ts=as_utc(bar.ts), open=bar.open, high=bar.high, low=bar.low, close=bar.close,
             pre_close=bar.pre_close, volume=bar.volume, amount=bar.amount, source=bar.source)
        for bar in bars if start <= as_utc(bar.ts) <= end
    ]
    changed = repo.upsert(db, symbol, period, rows)
    db.commit()
    if changed:
        from app.services.indicator_service import invalidate_indicator_cache
        from app.utils.market_cache import invalidate_search_cache
        from app.ws.publisher import publish_kline_refresh

        invalidate_indicator_cache(symbol.id, period)
        invalidate_search_cache()
        publish_kline_refresh(symbol.id, period)
    return {"fetched": len(rows), "added": changed, "confirmed_empty": not rows and confirmed}


def refresh_symbol(db, symbol, end=None):
    result = {}
    errors = {}
    for period in repo.PERIODS:
        try:
            result[period] = refresh_period(db, symbol, period, end=end)
            if not result[period]["fetched"]:
                errors[period] = "公开数据源未返回该区间数据"
        except ProviderError as exc:
            db.rollback()
            errors[period] = str(exc)
    return {"periods": result, "errors": errors}


def refresh_all():
    with get_session() as db:
        result = {symbol.code: refresh_symbol(db, symbol) for symbol in repo.symbols(db)}
    for code, item in result.items():
        if item["errors"]:
            logger.warning("大盘指数 %s 更新未完成: %s", code, item["errors"])
    return result
