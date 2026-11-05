"""境内固定指数及 A 股日 K 缺口检测与按交易日区间补拉。"""

from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.config import get_settings
from app.models.kline import Kline1d
from app.models.kline_quality import KlineQuality, TradingDay
from app.repositories import kline_repo
from app.utils import market_cache

settings = get_settings()
MAINLAND_MARKETS = {"SSE", "SZSE", "CSI"}


def is_a_share_stock(symbol) -> bool:
    code = symbol.code or ""
    return bool(
        symbol.type == "stock" and (
            (symbol.market == "SSE" and code.startswith(("60", "68")))
            or (symbol.market == "SZSE" and code.startswith(("00", "30")))
            or (symbol.market == "BSE" and code.startswith(("4", "8", "9")))
        )
    )


def eligible(symbol) -> bool:
    return bool(
        (symbol.is_fixed_index and symbol.type == "index" and symbol.market in MAINLAND_MARKETS)
        or is_a_share_stock(symbol)
    )


def _calendar(db, window_start: date, today: date) -> list[date] | None:
    """持久化交易日；源不可用时仅使用覆盖完整目标区间的已存日历。"""
    existing = list(db.scalars(select(TradingDay.day).order_by(TradingDay.day)))
    if not existing or existing[0] > window_start or existing[-1] < today:
        try:
            import akshare as ak

            frame = ak.tool_trade_date_hist_sina()
            dates = sorted({date.fromisoformat(str(x)[:10]) for x in frame["trade_date"]})
            if not dates or dates[0] > window_start or dates[-1] < today:
                return None
            db.execute(pg_insert(TradingDay).values([{"day": day} for day in dates]).on_conflict_do_nothing())
            db.commit()
            existing = dates
        except Exception:
            db.rollback()
            return None
    return [day for day in existing if window_start <= day <= today]


def _last_completed(days: list[date], now: datetime) -> date | None:
    local = now.astimezone(settings.tz)
    candidates = [day for day in days if day < local.date() or (day == local.date() and local.time() >= time(15, 30))]
    return candidates[-1] if candidates else None


def last_completed_mainland_day(db, now: datetime | None = None) -> date | None:
    """固定指数启动检查使用与缺口检测相同的交易日边界。"""
    now = now or datetime.now(UTC)
    today = now.astimezone(settings.tz).date()
    days = _calendar(db, today - timedelta(days=30), today)
    return _last_completed(days, now) if days else None


def _ranges(days: list[date], all_days: list[date]) -> list[tuple[date, date]]:
    positions = {day: i for i, day in enumerate(all_days)}
    result: list[tuple[date, date]] = []
    for day in days:
        if result and positions[day] == positions[result[-1][1]] + 1:
            result[-1] = (result[-1][0], day)
        else:
            result.append((day, day))
    return result


def get_quality(db, symbol_id: int, period: str) -> KlineQuality | None:
    return db.get(KlineQuality, (symbol_id, period))


def _fetch_gap_bars(provider, symbol_param, asset_type, first: date, last: date, required: set[date]):
    """短区间优先选轻量来源；失败再按项目既有优先级链降级。"""
    start = datetime.combine(first - timedelta(days=1), time(), UTC)
    end = datetime.combine(last + timedelta(days=1), time(), UTC)
    bars = []
    try:
        if asset_type == "index":
            from app.data_providers.sina import SinaProvider

            bars = SinaProvider().fetch_kline(symbol_param, "1d", start, end, asset_type)
        elif asset_type == "industry_index":
            from app.data_providers.ths import THSProvider

            bars = THSProvider().fetch_kline(symbol_param, "1d", start, end, asset_type)
    except Exception:
        pass
    found = {market_cache.as_utc(bar.ts).date(): bar for bar in bars if market_cache.as_utc(bar.ts).date() in required}
    if required - found.keys():
        fallback = provider.fetch_kline(symbol_param, "1d", start, end, asset_type)
        found.update({market_cache.as_utc(bar.ts).date(): bar for bar in fallback if market_cache.as_utc(bar.ts).date() in required})
    return list(found.values())


def quality_dict(row: KlineQuality | None) -> dict:
    if row is None:
        return {"status": "unchecked", "missing_count": 0, "missing_ranges": [], "checked_at": None}
    return {
        "status": row.status,
        "checked_from": row.checked_from.isoformat() if row.checked_from else None,
        "checked_to": row.checked_to.isoformat() if row.checked_to else None,
        "missing_before": row.missing_before,
        "recovered": row.recovered,
        "missing_count": row.missing_count,
        "missing_ranges": row.missing_ranges,
        "checked_at": row.checked_at.isoformat(),
    }


def check_and_repair(db, symbol, provider, *, now: datetime | None = None, full_watchlist_repair: bool = False) -> dict:
    """Record available history coverage without calendar gap scans or automatic repairs."""
    now = now or datetime.now(UTC)
    dates = list(db.scalars(select(Kline1d.ts).where(Kline1d.symbol_id == symbol.id).order_by(Kline1d.ts)))
    checked_from = dates[0].date() if dates else None
    last_day = dates[-1].date() if dates else None
    status = "complete" if dates else "unknown"
    missing = []
    before = added = 0
    quality = get_quality(db, symbol.id, "1d")
    if quality is None:
        quality = KlineQuality(symbol_id=symbol.id, period="1d", status=status, checked_at=now)
        db.add(quality)
    quality.status = status
    quality.checked_from = checked_from
    quality.checked_to = last_day
    quality.missing_before = before
    quality.recovered = before - len(missing)
    quality.missing_count = len(missing)
    quality.missing_ranges = []
    quality.checked_at = now
    db.flush()
    return {"status": status, "added": added, "missing_before": before, "recovered": quality.recovered, "missing_count": len(missing)}
