"""境内固定指数及 A 股日 K 缺口检测与按交易日区间补拉。"""

from datetime import UTC, datetime

from sqlalchemy import select

from app.core.config import get_settings
from app.models.kline import Kline1d
from app.models.kline_quality import KlineQuality

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


def check_and_repair(db, symbol, provider, *, now: datetime | None = None, full_watchlist_repair: bool = False) -> dict:
    """Record available history coverage without calendar gap scans or automatic repairs."""
    now = now or datetime.now(UTC)
    from app.services import market_policy, source_history
    query = select(Kline1d.ts).where(Kline1d.symbol_id == symbol.id)
    if not market_policy.history_storage_enabled():
        query = query.where(Kline1d.source == 'stockdb')
    dates = list(db.scalars(query.order_by(Kline1d.ts)))
    if not dates and market_policy.akshare_enabled():
        dates = [bar.ts for bar in (source_history.cached(symbol.id, '1d') or [])]
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
