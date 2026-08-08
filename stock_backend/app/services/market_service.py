"""行情查询服务：标的列表/搜索、K线、实时快照（合并特殊字段）。"""

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.kline import KLINE_MODELS
from app.models.snapshot import EtfPremium, IndexValuation, SnapshotRealtime, StockFundamental
from app.models.symbol import Symbol
from app.repositories import kline_repo, symbol_repo

logger = logging.getLogger(__name__)


def list_symbols(
    db: Session,
    type_: str | None = None,
    search: str | None = None,
    fixed_only: bool | None = None,
) -> list[Symbol]:
    return symbol_repo.list_symbols(db, type_=type_, search=search, fixed_only=fixed_only)


def search_symbols(db: Session, q: str, limit: int = 10) -> list[Symbol]:
    """6位代码/名称联想（已入库优先，代码精确命中优先）。"""
    q = q.strip()
    if not q:
        return []
    exact = db.scalars(select(Symbol).where(Symbol.code == q).order_by(Symbol.id).limit(limit)).all()
    if exact:
        return list(exact)
    like = f"%{q}%"
    return list(
        db.scalars(
            select(Symbol).where(Symbol.code.like(like) | Symbol.name.like(like)).order_by(Symbol.id).limit(limit)
        )
    )


def resolve_symbol_id(db: Session, symbol: str) -> int | None:
    """按代码解析 symbol_id；代码不存在时回退按 id 解析。"""
    sym = symbol_repo.get_by_code(db, symbol)
    if sym:
        return sym.id
    if symbol.isdigit():
        return int(symbol)
    return None


def get_kline(
    db: Session,
    symbol: str,
    period: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 1000,
    offset: int = 0,
) -> list:
    if period not in KLINE_MODELS:
        raise ValueError(f"unsupported period: {period}")
    symbol_id = resolve_symbol_id(db, symbol)
    if symbol_id is None:
        return []
    if end is None:
        end = datetime.now().astimezone()
    if start is None:
        # 默认取最近一年
        from datetime import timedelta

        start = end - timedelta(days=365)
    return kline_repo.get_bars(db, period, symbol_id, start, end, limit=limit, offset=offset)


def get_snapshots(db: Session, symbol_ids: list[int]) -> list[dict]:
    """批量实时快照，按类型合并特殊字段。"""
    if not symbol_ids:
        return []
    symbols = {s.id: s for s in db.scalars(select(Symbol).where(Symbol.id.in_(symbol_ids)))}
    snaps = {
        s.symbol_id: s for s in db.scalars(select(SnapshotRealtime).where(SnapshotRealtime.symbol_id.in_(symbol_ids)))
    }
    stock_ids = [sid for sid in symbols if symbols[sid].type == "stock"]
    etf_ids = [sid for sid in symbols if symbols[sid].type == "etf"]
    index_ids = [sid for sid in symbols if symbols[sid].type == "index"]
    fundamentals = {
        f.symbol_id: f for f in db.scalars(select(StockFundamental).where(StockFundamental.symbol_id.in_(stock_ids)))
    }
    premiums = {e.symbol_id: e for e in db.scalars(select(EtfPremium).where(EtfPremium.symbol_id.in_(etf_ids)))}
    valuations = {
        v.symbol_id: v for v in db.scalars(select(IndexValuation).where(IndexValuation.symbol_id.in_(index_ids)))
    }

    result: list[dict] = []
    for symbol_id in symbol_ids:
        sym = symbols.get(symbol_id)
        if sym is None:
            continue
        snap = snaps.get(symbol_id)
        item: dict = {
            "symbol_id": symbol_id,
            "code": sym.code,
            "name": sym.name,
            "type": sym.type,
        }
        if snap:
            item.update(
                {
                    "price": _num(snap.price),
                    "change": _num(snap.change),
                    "change_pct": _num(snap.change_pct),
                    "open": _num(snap.open),
                    "high": _num(snap.high),
                    "low": _num(snap.low),
                    "pre_close": _num(snap.pre_close),
                    "volume": snap.volume,
                    "amount": _num(snap.amount),
                    "turnover": _num(snap.turnover),
                    "amplitude": _num(snap.amplitude),
                    "updated_at": snap.updated_at,
                }
            )
        else:
            item.update(
                {
                    "price": None,
                    "change": None,
                    "change_pct": None,
                    "open": None,
                    "high": None,
                    "low": None,
                    "pre_close": None,
                    "volume": None,
                    "amount": None,
                    "turnover": None,
                    "amplitude": None,
                    "updated_at": None,
                }
            )
        extra: dict = {}
        if sym.type == "stock" and symbol_id in fundamentals:
            f = fundamentals[symbol_id]
            extra = {"market_cap": _num(f.market_cap), "pe": _num(f.pe)}
        elif sym.type == "etf" and symbol_id in premiums:
            e = premiums[symbol_id]
            extra = {"nav": _num(e.nav), "premium": _num(e.premium)}
        elif sym.type == "index" and symbol_id in valuations:
            v = valuations[symbol_id]
            extra = {"pe": _num(v.pe)}
        item["extra"] = extra
        result.append(item)
    return result


def _num(v):
    return float(v) if v is not None else None
