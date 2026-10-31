"""从本地日 K 生成周 K 和月 K，不增加外部行情请求。"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.data_providers.base import KlineBar
from app.repositories import kline_repo
from app.utils import market_cache

SHANGHAI = ZoneInfo("Asia/Shanghai")


def _aggregate(daily, period: str) -> list[KlineBar]:
    groups: list[KlineBar] = []
    current = None
    for row in daily:
        ts = market_cache.as_utc(row.ts)
        trading_day = ts.astimezone(SHANGHAI)
        key = trading_day.isocalendar()[:2] if period == "1w" else (trading_day.year, trading_day.month)
        if key != current:
            groups.append(KlineBar(ts, float(row.open), float(row.high), float(row.low),
                                   float(row.close), int(row.volume), float(row.amount)))
            current = key
        else:
            bar = groups[-1]
            bar.ts = ts
            bar.high = max(bar.high, float(row.high))
            bar.low = min(bar.low, float(row.low))
            bar.close = float(row.close)
            bar.volume += int(row.volume)
            bar.amount += float(row.amount)
    return groups


def weekly_bars(db, symbol_id: int, *, end: datetime | None = None) -> list[KlineBar]:
    daily = kline_repo.get_bars(db, "1d", symbol_id, datetime.min.replace(tzinfo=UTC),
                                end or datetime.now(UTC), limit=100000)
    return _aggregate(daily, "1w")


def get_period_bars(db, symbol_id: int, period: str, start: datetime | None,
                    end: datetime | None, limit: int, offset: int = 0) -> list[KlineBar]:
    """按完整自然周/月聚合；最新页只读必要的日 K，避免每次扫描全部历史。"""
    if period not in ("1w", "1mon"):
        raise ValueError(f"unsupported period: {period}")
    through = market_cache.as_utc(end) if end else datetime.now(UTC)
    if start is None and end is None:
        daily = kline_repo.latest_bars(db, "1d", symbol_id,
                                       limit=(limit + offset + 2) * (7 if period == "1w" else 32))
    else:
        from_ts = market_cache.as_utc(start) if start else datetime.min.replace(tzinfo=UTC)
        if start is None:
            first = from_ts
        elif period == "1w":
            local = from_ts.astimezone(SHANGHAI)
            first = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        else:
            first = from_ts.astimezone(SHANGHAI).replace(day=1, hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)
        daily = kline_repo.get_bars(db, "1d", symbol_id, first, through, limit=100000)
    bars = _aggregate((row for row in daily if market_cache.as_utc(row.ts) <= through), period)
    if start is not None:
        from_ts = market_cache.as_utc(start)
        bars = [bar for bar in bars if bar.ts >= from_ts]
    if start is None and end is None:
        return bars[-(limit + offset):][:limit] if offset else bars[-limit:]
    return bars[offset:offset + limit]


def get_weekly_bars(db, symbol_id: int, start: datetime | None, end: datetime | None,
                    limit: int, offset: int = 0) -> list[KlineBar]:
    return get_period_bars(db, symbol_id, "1w", start, end, limit, offset)
