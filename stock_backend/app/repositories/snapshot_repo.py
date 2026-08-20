"""实时快照读写（snapshot_realtime 表）。"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.data_providers.base import RealtimeQuote
from app.models.snapshot import EtfPremium, IndexValuation, SnapshotRealtime, StockFundamental


def _not_null(v, default=0):
    """NOT NULL 数值列兜底：None/空值写默认值（指数快照无成交量/额等场景）。"""
    return v if v is not None else default


def get_snapshot(db: Session, symbol_id: int) -> SnapshotRealtime | None:
    return db.get(SnapshotRealtime, symbol_id)


def get_updated_after(db: Session, since: datetime) -> dict[int, dict]:
    """断线补拉：返回 since 之后更新的快照 {symbol_id: {字段 dict}}（WS sync 用）。

    DB 列为 timestamp without time zone（naive UTC），入参 aware 时间先归一为 naive UTC。
    """
    from datetime import UTC

    from app.utils.market_cache import snapshot_to_cache_dict

    if since.tzinfo is not None:
        since = since.astimezone(UTC).replace(tzinfo=None)
    rows = db.scalars(
        select(SnapshotRealtime).where(SnapshotRealtime.updated_at >= since).order_by(SnapshotRealtime.updated_at)
    )
    return {r.symbol_id: snapshot_to_cache_dict(r) for r in rows}


def upsert_snapshot(db: Session, quote: RealtimeQuote) -> None:
    """按 symbol_id 幂等 upsert 实时快照（quote.extra 携带特殊字段）。"""
    if quote.price is None:
        return
    values = {
        "symbol_id": int(quote.extra.get("symbol_id", 0)),
        "price": quote.price,
        "change": _not_null(quote.change),
        "change_pct": _not_null(quote.change_pct),
        "open": quote.open,
        "high": quote.high,
        "low": quote.low,
        "pre_close": quote.pre_close,
        # volume/amount 保持 None 写 NULL：区分"数据源无此字段"（如海外指数）与"真实零成交"
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
