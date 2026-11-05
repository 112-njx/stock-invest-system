"""K 线读写（kline_* 分区表，幂等 upsert）。"""

from datetime import datetime, timedelta

from sqlalchemy import Date, case, delete, exists, func, or_, select
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
    changed = 0
    if period in {'1w', '1mon'}:
        # Native index output can include several labels within one period
        # when constituent trading calendars differ. Keep its latest record;
        # prices and volume are used verbatim, with no local aggregation.
        def period_key(bar):
            day = bar.ts.date()
            return (bar.source, day.isocalendar()[:2] if period == '1w' else (day.year, day.month))
        bars = list({period_key(bar): bar for bar in sorted(bars, key=lambda bar: bar.ts)}.values())
        # SDK labels an unfinished period with its latest trading day. Replace
        # the earlier label when that same source period advances; do not aggregate.
        unit = 'week' if period == '1w' else 'month'
        for source in {bar.source for bar in bars}:
            stamps = [bar.ts for bar in bars if bar.source == source]
            groups = {stamp.date() - timedelta(days=stamp.weekday())
                      if unit == 'week' else stamp.date().replace(day=1) for stamp in stamps}
            changed += db.execute(delete(model).where(
                model.symbol_id == symbol_id, model.source == source,
                func.date_trunc(unit, model.ts).cast(Date).in_(groups),
                model.ts.not_in(stamps),
            )).rowcount or 0
    rows = list({
        (b.ts, b.source): {
            "source": b.source,
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
    for offset in range(0, len(rows), 1000):
        stmt = pg_insert(model).values(rows[offset:offset + 1000])
        fields = ("open", "high", "low", "close", "volume", "amount")
        stmt = stmt.on_conflict_do_update(
            index_elements=["symbol_id", "ts", "source"],
            set_={field: getattr(stmt.excluded, field) for field in fields},
            where=or_(*(getattr(model, field).is_distinct_from(getattr(stmt.excluded, field)) for field in fields)),
        )
        changed += db.execute(stmt).rowcount or 0
    return changed


def source_filter(model, symbol_id):
    from app.services.market_policy import akshare_enabled
    if not akshare_enabled():
        return model.source == "stockdb"
    local = model.__table__.alias("local_history")
    has_local = exists(select(1).select_from(local).where(
        local.c.symbol_id == symbol_id, local.c.source == "stockdb"
    ))
    # Select a whole source for the series; never splice AkShare rows into local history.
    return model.source == case((has_local, "stockdb"), else_="akshare")


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
        .where(model.symbol_id == symbol_id, source_filter(model, symbol_id), model.ts >= start, model.ts <= end)
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
        .where(model.symbol_id == symbol_id, source_filter(model, symbol_id))
        .order_by(model.ts.desc())
        .limit(limit)
    )
    rows = list(db.scalars(stmt))
    rows.reverse()
    return rows


def latest_ts(db: Session, period: str, symbol_id: int) -> datetime | None:
    model = _model(period)
    return db.scalar(select(model.ts).where(model.symbol_id == symbol_id, source_filter(model, symbol_id)).order_by(model.ts.desc()).limit(1))
