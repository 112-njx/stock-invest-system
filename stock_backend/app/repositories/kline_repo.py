"""K 线读写（kline_* 分区表，幂等 upsert）。"""

from datetime import datetime, timedelta

from sqlalchemy import Date, and_, case, delete, exists, func, or_, select
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
    from app.services.market_policy import history_storage_enabled
    if not history_storage_enabled():
        bars = [bar for bar in bars if bar.source != 'akshare']
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


def source_filter(model, symbol_id, start=None, end=None):
    from app.services.market_policy import akshare_enabled, history_storage_enabled
    if not akshare_enabled() or not history_storage_enabled():
        return model.source == "stockdb"
    local = model.__table__.alias("local_history")
    if start is not None or end is not None:
        def bounds(source):
            conditions = [local.c.symbol_id == symbol_id, local.c.source == source]
            if start is not None:
                conditions.append(local.c.ts >= start)
            if end is not None:
                conditions.append(local.c.ts <= end)
            return tuple(select(aggregate(local.c.ts)).where(*conditions).scalar_subquery()
                         for aggregate in (func.min, func.max))

        local_first, local_last = bounds('stockdb')
        remote_first, remote_last = bounds('akshare')
        # Pick one source for the requested window, including indicator warmup.
        # Never replace individual bars across different qfq bases.
        remote_covers_more = and_(
            remote_first <= local_first, remote_last >= local_last,
            or_(remote_first < local_first, remote_last > local_last),
        )
        return model.source == case(
            (or_(local_first.is_(None), remote_covers_more), 'akshare'), else_='stockdb'
        )
    has_local = exists(select(1).select_from(local).where(
        local.c.symbol_id == symbol_id, local.c.source == "stockdb"
    ))
    # Select a whole source for the series; never splice AkShare rows into local history.
    return model.source == case((has_local, "stockdb"), else_="akshare")


def use_transient_source(db, model, symbol_id, start=None, end=None):
    from app.services import market_policy, source_history
    policy = market_policy.read()
    if not policy['akshare_enabled'] or policy['history_storage_enabled']:
        return False
    conditions = [model.symbol_id == symbol_id, model.source == 'stockdb']
    if start is not None:
        conditions.append(model.ts >= start)
    if end is not None:
        conditions.append(model.ts <= end)
    first, last = db.execute(select(func.min(model.ts), func.max(model.ts)).where(*conditions)).one()
    if first is None:
        return True
    if start is None and end is None:
        return False
    from app.utils.market_cache import as_utc
    remote = [bar for bar in (source_history.cached(symbol_id, next(k for k,v in KLINE_MODELS.items() if v is model)) or [])
              if (start is None or as_utc(bar.ts) >= as_utc(start)) and (end is None or as_utc(bar.ts) <= as_utc(end))]
    return bool(remote and as_utc(remote[0].ts) <= as_utc(first) and as_utc(remote[-1].ts) >= as_utc(last)
                and (as_utc(remote[0].ts) < as_utc(first) or as_utc(remote[-1].ts) > as_utc(last)))


def get_bars(
    db: Session,
    period: str,
    symbol_id: int,
    start: datetime,
    end: datetime,
    limit: int = 1000,
    offset: int = 0,
    source_window: tuple[datetime, datetime] | None = None,
) -> list:
    model = _model(period)
    if use_transient_source(db, model, symbol_id, *(source_window or (start, end))):
        from app.services.source_history import window
        return window(db, symbol_id, period, start, end, limit, offset)
    stmt = (
        select(model)
        .where(model.symbol_id == symbol_id,
               source_filter(model, symbol_id, *(source_window or (start, end))),
               model.ts >= start, model.ts <= end)
        .order_by(model.ts)
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def latest_bars(db: Session, period: str, symbol_id: int, limit: int = 1000) -> list:
    """最近 N 根 K 线（返回按 ts 升序），供"最新N根"缓存与默认查询。"""
    model = _model(period)
    if use_transient_source(db, model, symbol_id):
        from app.services.source_history import cached
        return (cached(symbol_id, period) or [])[-limit:]
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
    if use_transient_source(db, model, symbol_id):
        from app.services.source_history import cached
        rows = cached(symbol_id, period) or []
        return rows[-1].ts if rows else None
    return db.scalar(select(model.ts).where(model.symbol_id == symbol_id, source_filter(model, symbol_id)).order_by(model.ts.desc()).limit(1))
