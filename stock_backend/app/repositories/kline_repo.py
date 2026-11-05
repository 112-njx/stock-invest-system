"""K 线读写（kline_* 分区表，幂等 upsert）。"""

from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.data_providers.base import KlineBar
from app.models.kline import KLINE_MODELS


def _model(period: str):
    model = KLINE_MODELS.get(period)
    if model is None:
        raise ValueError(f"unsupported period: {period}")
    return model


def upsert_bars(db: Session, period: str, symbol_id: int, bars: list[KlineBar]) -> int:
    """幂等写入：按 (symbol_id, ts) 更新变化记录（支持前复权历史刷新）。"""
    if not bars:
        return 0
    model = _model(period)
    rows = list({
        b.ts: {
            "symbol_id": symbol_id,
            "ts": b.ts,
            "open": b.open,
            "high": b.high,
            "low": b.low,
            "close": b.close,
            "volume": b.volume,
            "amount": b.amount,
        }
        for b in bars
    }.values())
    changed = 0
    for offset in range(0, len(rows), 1000):
        stmt = pg_insert(model).values(rows[offset:offset + 1000])
        fields = ("open", "high", "low", "close", "volume", "amount")
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol_id", "ts"],
            set_={field: getattr(stmt.excluded, field) for field in fields},
            where=or_(*(getattr(model, field).is_distinct_from(getattr(stmt.excluded, field)) for field in fields)),
        )
        changed += db.execute(stmt).rowcount or 0
    return changed


def get_bars(
    db: Session,
    period: str,
    symbol_id: int,
    start: datetime,
    end: datetime,
    limit: int = 1000,
    offset: int = 0,
) -> list:
    model = _model(period)
    stmt = (
        select(model)
        .where(model.symbol_id == symbol_id, model.ts >= start, model.ts <= end)
        .order_by(model.ts)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def latest_bars(db: Session, period: str, symbol_id: int, limit: int = 1000) -> list:
    """最近 N 根 K 线（返回按 ts 升序），供"最新N根"缓存与默认查询。"""
    model = _model(period)
    stmt = (
        select(model)
        .where(model.symbol_id == symbol_id)
        .order_by(model.ts.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt))
    rows.reverse()
    return rows


def latest_ts(db: Session, period: str, symbol_id: int) -> datetime | None:
    model = _model(period)
    return db.scalar(select(model.ts).where(model.symbol_id == symbol_id).order_by(model.ts.desc()).limit(1))
