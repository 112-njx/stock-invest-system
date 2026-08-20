"""K 线读写（kline_* 分区表，幂等 upsert）。"""

from datetime import datetime

from sqlalchemy import select
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
    """幂等写入：按 (symbol_id, ts) 冲突忽略（重复同步不产生脏数据）。"""
    if not bars:
        return 0
    model = _model(period)
    rows = [
        {
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
    ]
    stmt = pg_insert(model).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["symbol_id", "ts"])
    result = db.execute(stmt)
    return result.rowcount or 0


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
