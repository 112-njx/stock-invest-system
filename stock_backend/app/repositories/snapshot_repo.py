"""实时快照读写（snapshot_realtime 表）。"""

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.data_providers.base import RealtimeQuote
from app.models.snapshot import EtfPremium, IndexValuation, SnapshotRealtime, StockFundamental


def upsert_snapshot(db: Session, quote: RealtimeQuote) -> None:
    """按 symbol_id 幂等 upsert 实时快照（quote.extra 携带特殊字段）。"""
    if quote.price is None:
        return
    values = {
        "symbol_id": int(quote.extra.get("symbol_id", 0)),
        "price": quote.price,
        "change": quote.change,
        "change_pct": quote.change_pct,
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "pre_close": quote.pre_close,
        "volume": quote.volume,
        "amount": quote.amount,
        "turnover": quote.turnover,
        "amplitude": quote.amplitude,
        "updated_at": quote.updated_at or datetime.now(UTC),
    }
    if not values["symbol_id"]:
        return
    stmt = pg_insert(SnapshotRealtime).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=[SnapshotRealtime.symbol_id],
        set_={k: v for k, v in values.items() if k != "symbol_id"},
    )
    db.execute(stmt)


def upsert_fundamentals(db: Session, symbol_id: int, market_cap, pe) -> None:
    if symbol_id is None:
        return
    stmt = pg_insert(StockFundamental).values(symbol_id=symbol_id, market_cap=market_cap, pe=pe)
    stmt = stmt.on_conflict_do_update(
        index_elements=[StockFundamental.symbol_id],
        set_={"market_cap": market_cap, "pe": pe, "updated_at": datetime.now(UTC)},
    )
    db.execute(stmt)


def upsert_etf_premium(db: Session, symbol_id: int, nav, premium) -> None:
    if symbol_id is None:
        return
    stmt = pg_insert(EtfPremium).values(symbol_id=symbol_id, nav=nav, premium=premium)
    stmt = stmt.on_conflict_do_update(
        index_elements=[EtfPremium.symbol_id],
        set_={"nav": nav, "premium": premium, "updated_at": datetime.now(UTC)},
    )
    db.execute(stmt)


def upsert_index_valuation(db: Session, symbol_id: int, pe) -> None:
    if symbol_id is None:
        return
    stmt = pg_insert(IndexValuation).values(symbol_id=symbol_id, pe=pe)
    stmt = stmt.on_conflict_do_update(
        index_elements=[IndexValuation.symbol_id],
        set_={"pe": pe, "updated_at": datetime.now(UTC)},
    )
    db.execute(stmt)
