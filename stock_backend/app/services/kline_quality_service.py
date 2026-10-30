"""境内固定指数日 K 缺口检测与按交易日区间补拉。"""

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


def eligible(symbol) -> bool:
    return bool(symbol.is_fixed_index and symbol.type == "index" and symbol.market in MAINLAND_MARKETS)


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


def check_and_repair(db, symbol, provider, *, now: datetime | None = None) -> dict:
    """只处理境内固定指数的日 K；不使用工作日猜测交易日。"""
    if not eligible(symbol):
        return {"status": "unsupported", "added": 0}
    now = now or datetime.now(UTC)
    window_start = (now - timedelta(days=settings.KLINE_INIT_DAYS)).astimezone(settings.tz).date()
    calendar = _calendar(db, window_start, now.astimezone(settings.tz).date())
    last_day = _last_completed(calendar, now) if calendar else None
    rows = list(db.scalars(select(Kline1d.ts).where(Kline1d.symbol_id == symbol.id, Kline1d.ts >= datetime.combine(window_start, time(), UTC)).order_by(Kline1d.ts)))
    actual = {market_cache.as_utc(ts).date() for ts in rows}
    checked_from = min(actual) if actual else window_start
    expected = [day for day in (calendar or []) if checked_from <= day <= last_day] if last_day else []
    missing = [day for day in expected if day not in actual]
    before = len(missing)
    added = 0
    if calendar and last_day and missing:
        from app.services.sync_service import _provider_params

        symbol_param, asset_type = _provider_params(symbol)
        for first, last in _ranges(missing, expected):
            # 含两端缓冲，兼容提供器日期边界及周末。
            try:
                bars = provider.fetch_kline(
                    symbol_param, "1d", datetime.combine(first - timedelta(days=1), time(), UTC),
                    datetime.combine(last + timedelta(days=1), time(), UTC), asset_type,
                )
                added += kline_repo.upsert_bars(db, "1d", symbol.id, bars)
            except Exception:
                db.rollback()
                added = 0
                break
        db.commit()
        actual = {market_cache.as_utc(ts).date() for ts in db.scalars(
            select(Kline1d.ts).where(Kline1d.symbol_id == symbol.id, Kline1d.ts >= datetime.combine(window_start, time(), UTC))
        )}
        missing = [day for day in expected if day not in actual]
        if added:
            from app.services.indicator_service import invalidate_indicator_cache
            from app.ws.publisher import publish_kline_refresh

            market_cache.invalidate_kline_cache(symbol.id, "1d")
            invalidate_indicator_cache(symbol.id, "1d")
            publish_kline_refresh(symbol.id, "1d")
    status = "unknown" if not calendar or not last_day else "partial" if missing else "complete"
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
    quality.missing_ranges = [[a.isoformat(), b.isoformat()] for a, b in _ranges(missing, expected)]
    quality.checked_at = now
    db.commit()
    return {"status": status, "added": added, "missing_before": before, "recovered": quality.recovered, "missing_count": len(missing)}
