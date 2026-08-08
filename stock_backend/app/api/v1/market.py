"""行情查询 API：标的列表/搜索、K线、批量实时快照。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.schemas.market import KlineBarOut, SnapshotOut, SymbolOut
from app.services import market_service

router = APIRouter(prefix="/api/v1", tags=["market"])


@router.get("/symbols")
def list_symbols(
    type_: str | None = Query(None, alias="type", description="stock/etf/index"),
    search: str | None = Query(None, description="代码/名称模糊过滤"),
    is_fixed: int | None = Query(None, description="1=仅固定指数（G/H 区）"),
    db: Session = Depends(get_db),
) -> dict:
    symbols = market_service.list_symbols(
        db, type_=type_, search=search, fixed_only=bool(is_fixed) if is_fixed is not None else None
    )
    return ok(data=[SymbolOut.model_validate(s).model_dump() for s in symbols])


@router.get("/symbols/search")
def search_symbols(
    q: str = Query(..., min_length=1, max_length=64, description="6位代码或名称"),
    db: Session = Depends(get_db),
) -> dict:
    symbols = market_service.search_symbols(db, q)
    return ok(data=[SymbolOut.model_validate(s).model_dump() for s in symbols])


@router.get("/kline")
def get_kline(
    symbol: str = Query(..., description="标的代码（或 symbol_id）"),
    period: str = Query("1d", pattern="^(15m|1d|1w|1mon)$"),
    start: datetime | None = Query(None, description="开始时间（UTC）"),
    end: datetime | None = Query(None, description="结束时间（UTC）"),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> dict:
    try:
        bars = market_service.get_kline(db, symbol, period, start, end, limit=limit, offset=offset)
    except ValueError as exc:
        raise ApiError(status_code=400, msg=str(exc)) from exc
    data = [
        KlineBarOut(
            ts=b.ts,
            open=float(b.open),
            high=float(b.high),
            low=float(b.low),
            close=float(b.close),
            volume=b.volume,
            amount=float(b.amount),
        ).model_dump(mode="json")
        for b in bars
    ]
    return ok(data=data)


@router.get("/snapshot")
def get_snapshot(
    symbols: str = Query(..., description="逗号分隔的 symbol_id 列表"),
    db: Session = Depends(get_db),
) -> dict:
    try:
        ids = [int(x) for x in symbols.split(",") if x.strip()]
    except ValueError as exc:
        raise ApiError(status_code=400, msg="symbols 必须为逗号分隔的数字 ID") from exc
    snapshots = market_service.get_snapshots(db, ids)
    return ok(data=[SnapshotOut(**s).model_dump(mode="json") for s in snapshots])
