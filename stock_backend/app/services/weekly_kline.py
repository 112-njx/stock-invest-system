"""从本地日 K 生成周 K，不增加外部行情请求。"""

from datetime import UTC, datetime

from app.data_providers.base import KlineBar
from app.repositories import kline_repo
from app.utils import market_cache


def weekly_bars(db, symbol_id: int, *, end: datetime | None = None) -> list[KlineBar]:
    """按上海交易日所在的自然周聚合，时间戳采用该周最后一个交易日。"""
    daily = kline_repo.get_bars(
        db, "1d", symbol_id, datetime.min.replace(tzinfo=UTC),
        end or datetime.now(UTC), limit=100000,
    )
    groups: list[KlineBar] = []
    week = None
    for row in daily:
        ts = market_cache.as_utc(row.ts)
        key = ts.isocalendar()[:2]
        if key != week:
            groups.append(KlineBar(ts, float(row.open), float(row.high), float(row.low),
                                   float(row.close), int(row.volume), float(row.amount)))
            week = key
        else:
            bar = groups[-1]
            bar.ts = ts
            bar.high = max(bar.high, float(row.high))
            bar.low = min(bar.low, float(row.low))
            bar.close = float(row.close)
            bar.volume += int(row.volume)
            bar.amount += float(row.amount)
    return groups


def get_weekly_bars(db, symbol_id: int, start: datetime | None, end: datetime | None,
                    limit: int, offset: int = 0) -> list[KlineBar]:
    # 显式区间向前扩到周一，保证边界一周的 OHLC 不被截断。
    from_ts = market_cache.as_utc(start) if start else None
    through = market_cache.as_utc(end) if end else None
    bars = weekly_bars(db, symbol_id, end=through)
    if from_ts is not None:
        bars = [bar for bar in bars if bar.ts >= from_ts]
    if through is not None:
        bars = [bar for bar in bars if bar.ts <= through]
    if start is None and end is None and offset == 0:
        return bars[-limit:]
    return bars[offset:offset + limit]
