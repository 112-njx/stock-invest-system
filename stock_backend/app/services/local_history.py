"""Stock and ETF history from the local StockDB reader and SDK."""

from datetime import UTC, datetime, timedelta

from app.data_providers.base import ProviderError, daily_session_close
from app.data_providers.stockdb import StockDBProvider
from app.utils.market_cache import as_utc

FIRST = datetime(1900, 1, 1, tzinfo=UTC)
MINUTE_BARS = {"1m": 240, "5m": 48, "15m": 16, "30m": 8, "60m": 4}


def read(symbol, period, start, end, *, limit=1000, confirmed_at=None):
    provider = StockDBProvider()
    if symbol is None or not provider.can_fetch_kline(symbol.type, period):
        return []
    end = as_utc(end)
    start = as_utc(start)
    if start is None and period in MINUTE_BARS:
        keys = provider.query("keys", "分钟k", k1=f"key:{symbol.code}", k2="all:", num=-1)
        if not keys:
            return []
        day = datetime.strptime(keys[-1].rsplit(":", 1)[-1][:8], "%Y%m%d").replace(tzinfo=UTC)
        days = max(30, (limit * 2) // MINUTE_BARS[period] + 14)
        start = min(day, end) - timedelta(days=days)
    start = start or FIRST
    if start > end:
        return []
    cutoff = provider.daily_confirmation_cutoff(confirmed_at) if confirmed_at is not None else None
    bars = provider.fetch_kline(symbol.code, period, start, end, symbol.type)
    if confirmed_at is not None:
        if cutoff != provider.daily_confirmation_cutoff(confirmed_at):
            raise ProviderError("StockDB 数据版本已更新，请重试")
        for bar in bars:
            bar.close_confirmed = cutoff is not None and cutoff >= daily_session_close(bar.ts)
    return sorted((bar for bar in bars if start <= bar.ts <= end), key=lambda bar: bar.ts)
