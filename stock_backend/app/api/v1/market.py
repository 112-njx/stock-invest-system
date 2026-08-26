"""行情查询 API：标的列表/搜索、K线、批量实时快照。"""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.models.user import User
from app.repositories import ops_repo, user_repo
from app.schemas.market import KlineBarOut, SnapshotOut, SymbolOut, SymbolSearchOut
from app.services import market_service, sync_service
from app.utils import market_cache

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
    type: str | None = Query(None, description="stock/etf/index 过滤"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    symbols = market_service.search_symbols(db, q, type_=type, limit=limit)
    return ok(data=[SymbolSearchOut(**s).model_dump(mode="json") for s in symbols])


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
    data = [KlineBarOut(**b).model_dump(mode="json") for b in bars]
    return ok(data=data)


@router.get("/snapshot")
def get_snapshot(
    symbols: str = Query(..., description="逗号分隔的 symbol_id 列表"),
    db: Session = Depends(get_db),
    current: User | None = Depends(get_current_user_optional),
) -> dict:
    try:
        ids = [int(x) for x in symbols.split(",") if x.strip()]
    except ValueError as exc:
        raise ApiError(status_code=400, msg="symbols 必须为逗号分隔的数字 ID") from exc
    if current is not None:
        watch_ids = set(user_repo.list_watchlist_symbol_ids(db, current.id))
        if watch_ids and set(ids) <= watch_ids:
            cached = market_cache.get_watchlist_snap_cache(current.id)
            if cached is not None:
                return ok(data=[SnapshotOut(**s).model_dump(mode="json") for s in cached])
            snapshots = market_service.get_snapshots(db, ids)
            ttl = 10 if sync_service.is_market_open() else 300  # 交易时段 10s / 非交易 300s
            market_cache.set_watchlist_snap_cache(current.id, snapshots, ttl)
            return ok(data=[SnapshotOut(**s).model_dump(mode="json") for s in snapshots])
    snapshots = market_service.get_snapshots(db, ids)
    return ok(data=[SnapshotOut(**s).model_dump(mode="json") for s in snapshots])


@router.get("/sync-status")
def get_sync_status(
    scope: str = Query("fixed_indices", description="fixed_indices/catalog/watchlist 同步范围"),
    db: Session = Depends(get_db),
) -> dict:
    """同步状态查询（V0.2 1.1）：前端行情页轮询固定指数预同步进度（X/49）。"""
    row = ops_repo.get_latest_sync_status(db, scope)
    if row is None:
        return ok(data={"status": "done", "progress": 100, "total": 0, "message": "无进行中的同步"})
    return ok(
        data={
            "status": row.status,
            "progress": row.progress,
            "total": row.total,
            "message": row.message,
        }
    )


@router.post("/fetch-all")
def fetch_all() -> dict:
    """一次性全量同步（免鉴权，本地测试/运维用）：固定指数K线+快照 + 全量实时快照，同步执行不依赖 Celery/beat。

    用于本地无法触发定时任务时一次性补齐大盘/行业指数数据，返回固定指数同步结果与实时轮询结果。
    """
    fixed = sync_service.run_fixed_indices_sync()
    realtime = sync_service.run_realtime_poll()
    return ok(data={"fixed_indices": fixed, "realtime": realtime}, msg="全量同步完成")
