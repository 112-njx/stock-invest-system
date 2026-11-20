from datetime import timedelta

from sqlalchemy import Date, delete, func, or_, select, text, tuple_
from sqlalchemy.dialects.postgresql import insert

from app.models.market_index_bar import MarketIndexBar as Bar
from app.models.symbol import Symbol

# Database identity -> QFile/Parquet market. Shenzhen equity 000001 is a different symbol.
QMT_MARKETS = {
    ("SSE", "000001"): "SH", ("CSI", "000300"): "SH", ("SZSE", "399006"): "SZ",
    ("SSE", "000688"): "SH", ("SZSE", "399001"): "SZ", ("SSE", "000016"): "SH",
    ("CSI", "000852"): "SH", ("CSI", "000905"): "SH",
}
PERIODS = ("1d", "15m", "1w", "1mon")


def handles(symbol):
    return (symbol is not None and symbol.type == "index" and symbol.is_fixed_index
            and (symbol.market, symbol.code) in QMT_MARKETS)


def symbols(db):
    return list(db.scalars(select(Symbol).where(
        Symbol.type == "index", Symbol.is_fixed_index.is_(True),
        tuple_(Symbol.market, Symbol.code).in_(list(QMT_MARKETS)),
    ).order_by(Symbol.sort_order)))


def bars(db, symbol_id, period, start=None, end=None, limit=1000, offset=0, *, latest=False):
    stmt = select(Bar).where(Bar.symbol_id == symbol_id, Bar.period == period)
    if start is not None:
        stmt = stmt.where(Bar.ts >= start)
    if end is not None:
        stmt = stmt.where(Bar.ts <= end)
    rows = list(db.scalars(stmt.order_by(Bar.ts.desc() if latest else Bar.ts).limit(limit).offset(offset)))
    return rows[::-1] if latest else rows


def coverage(db, symbol_id, period):
    return db.execute(select(func.min(Bar.ts), func.max(Bar.ts)).where(
        Bar.symbol_id == symbol_id, Bar.period == period,
    )).one()


def version(db):
    stamp = db.scalar(select(Bar.updated_at).order_by(Bar.updated_at.desc()).limit(1))
    return stamp.isoformat() if stamp else None


def upsert(db, symbol, period, rows, *, initial=False):
    if not handles(symbol) or period not in PERIODS:
        raise ValueError("不在行情页大盘指数同步范围内")
    if not rows:
        return 0
    # Serialize writes so the committed revision always advances in commit order.
    db.execute(text("SELECT pg_advisory_xact_lock(4000000002)"))
    by_timestamp = {row["ts"]: row for row in rows}
    if period in {"1w", "1mon"}:
        by_group = {}
        for ts in sorted(by_timestamp):
            day = ts.date()
            first = day - timedelta(days=day.weekday()) if period == "1w" else day.replace(day=1)
            by_group[first] = ts
        unit = "week" if period == "1w" else "month"
        # Older responses must not replace a later label for the same period.
        group_date = func.date_trunc(unit, func.timezone("UTC", Bar.ts)).cast(Date)
        existing = db.scalars(select(Bar.ts).where(
            Bar.symbol_id == symbol.id, Bar.period == period,
            group_date.in_(by_group),
        ))
        for ts in existing:
            day = ts.date()
            first = day - timedelta(days=day.weekday()) if period == "1w" else day.replace(day=1)
            if first in by_group and ts > by_group[first]:
                del by_group[first]
        by_timestamp = {ts: by_timestamp[ts] for ts in by_group.values()}
        if by_group:
            db.execute(delete(Bar).where(
                Bar.symbol_id == symbol.id, Bar.period == period,
                group_date.in_(by_group),
                Bar.ts.not_in(by_timestamp),
            ))
    items = [{**by_timestamp[ts], "symbol_id": symbol.id, "period": period} for ts in sorted(by_timestamp)]
    changed = 0
    for offset in range(0, len(items), 1000):
        stmt = insert(Bar).values(items[offset:offset + 1000])
        if initial:
            stmt = stmt.on_conflict_do_nothing()
        else:
            fields = {field: getattr(stmt.excluded, field) for field in
                      ("open", "high", "low", "close", "volume", "amount", "source")}
            for field in ("pre_close", "volume", "amount"):
                fields[field] = func.coalesce(func.nullif(getattr(stmt.excluded, field), 0), getattr(Bar, field))
            stmt = stmt.on_conflict_do_update(
                index_elements=["symbol_id", "period", "ts"],
                set_={**fields, "updated_at": func.clock_timestamp()},
                where=or_(*(getattr(Bar, field).is_distinct_from(value) for field, value in fields.items())),
            )
        changed += db.execute(stmt).rowcount or 0
    return changed
