"""Stored daily coverage for the remaining index sync workflow."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from app.models.kline import Kline1d
from app.models.kline_quality import KlineQuality

MAINLAND_MARKETS = {"SSE", "SZSE", "CSI"}


def eligible(symbol) -> bool:
    return symbol.is_fixed_index and symbol.type == "index" and symbol.market in MAINLAND_MARKETS


def get_quality(db, symbol_id: int, period: str) -> KlineQuality | None:
    return db.get(KlineQuality, (symbol_id, period))


def quality_dict(row: KlineQuality | None) -> dict:
    if row is None:
        return {"status": "unchecked", "checked_at": None}
    return {
        "status": row.status,
        "checked_from": row.checked_from.isoformat() if row.checked_from else None,
        "checked_to": row.checked_to.isoformat() if row.checked_to else None,
        "checked_at": row.checked_at.isoformat(),
    }


def record_coverage(db, symbol_id: int) -> bool:
    from app.services.source_history import cached

    first, last = db.execute(select(func.min(Kline1d.ts), func.max(Kline1d.ts)).where(
        Kline1d.symbol_id == symbol_id, Kline1d.source == "stockdb",
    )).one()
    if last is None:
        bars = cached(symbol_id, "1d")
        if bars:
            first, last = bars[0].ts, bars[-1].ts
    coverage = get_quality(db, symbol_id, "1d")
    if coverage is None:
        coverage = KlineQuality(symbol_id=symbol_id, period="1d")
        db.add(coverage)
    coverage.status = "complete" if last is not None else "unknown"
    coverage.checked_from = first.date() if first is not None else None
    coverage.checked_to = last.date() if last is not None else None
    coverage.checked_at = datetime.now(UTC)
    db.flush()
    return last is not None
