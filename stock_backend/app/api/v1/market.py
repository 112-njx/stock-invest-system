"""行情查询 API：标的列表/搜索、K线、批量实时快照。"""

from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user_optional, get_read_db
from app.core.exceptions import ApiError
from app.core.response import ok
from app.models.symbol import Symbol
from app.models.user import User
from app.repositories import ops_repo, user_repo
from app.schemas.market import KlineBarOut, SnapshotOut, SymbolOut, SymbolSearchOut
from app.services import market_service, sync_service
from app.utils import market_cache

router = APIRouter(prefix="/api/v1", tags=["market"])


class KlineBackfillRequest(BaseModel):
    symbol_id: int
    period: str
    start: datetime
    end: datetime
    retry: bool = False


@router.post("/kline/backfill")
def request_kline_backfill(payload: KlineBackfillRequest, db: Session = Depends(get_read_db)) -> dict:
    """只接受单个历史窗口；重复请求复用同一 Celery 任务。"""
    if payload.period not in ("15m", "1d", "1w", "1mon") or payload.start.tzinfo is None or payload.end.tzinfo is None:
        raise ApiError(status_code=400, msg="无效的周期或时区")
    if not timedelta(0) < payload.end - payload.start <= timedelta(days=100) or payload.end > datetime.now(payload.end.tzinfo):
        raise ApiError(status_code=400, msg="历史区间须在过去且不超过100天")
    if db.get(Symbol, payload.symbol_id) is None:
        raise ApiError(status_code=404, msg="标的不存在")
    from app.utils.redis_client import get_redis_client
    from app.worker.tasks.sync_tasks import kline_backfill

    key = f"kline-backfill:{payload.symbol_id}:{payload.period}:{payload.start.isoformat()}:{payload.end.isoformat()}"
    redis = get_redis_client()
    if payload.retry:
        existing = redis.get(key)
        if existing:
            from app.worker.celery_app import celery_app

            if celery_app.AsyncResult(existing).ready():
                redis.delete(key)
    task_id = str(uuid4())
    if not redis.set(key, task_id, ex=300, nx=True):
        return ok(data={"task_id": redis.get(key)})
    try:
        kline_backfill.apply_async(
            args=(payload.symbol_id, payload.period, payload.start.isoformat(), payload.end.isoformat()),
            task_id=task_id,
        )
    except Exception:
        redis.delete(key)
        raise
    return ok(data={"task_id": task_id})


@router.get("/kline/backfill/{task_id}")
def kline_backfill_status(task_id: str) -> dict:
    from app.worker.celery_app import celery_app

    result = celery_app.AsyncResult(task_id)
    if result.failed():
        return ok(data={"status": "failed"})
    if result.ready():
        return ok(data={"status": "done", "fetched": (result.result or {}).get("fetched", 0)})
    return ok(data={"status": "loading"})


@router.get("/symbols")
def list_symbols(
    type_: str | None = Query(None, alias="type", description="stock/etf/index"),
    search: str | None = Query(None, description="代码/名称模糊过滤"),
    is_fixed: int | None = Query(None, description="1=仅固定指数（G/H 区）"),
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
) -> dict:
    symbols = market_service.search_symbols(db, q, type_=type, limit=limit)
    return ok(data=[SymbolSearchOut(**s).model_dump(mode="json") for s in symbols])


@router.get("/market/home-indices")
def home_indices(db: Session = Depends(get_read_db)) -> dict:
    """首页固定指数：一次返回排序信息和已有快照，不触发外部行情同步。"""
    symbols = market_service.list_symbols(db, type_="index", fixed_only=True)
    snapshots = {s["symbol_id"]: s for s in market_service.get_snapshots(db, [s.id for s in symbols])}
    return ok(data=[
        {
            **SymbolOut.model_validate(symbol).model_dump(),
            "snapshot": SnapshotOut(**snapshots[symbol.id]).model_dump(mode="json")
            if symbol.id in snapshots else None,
        }
        for symbol in symbols
    ])


@router.get("/kline")
def get_kline(
    symbol: str = Query(..., description="标的代码（或 symbol_id）"),
    period: str = Query("1d", pattern="^(15m|1d|1w|1mon)$"),
    start: datetime | None = Query(None, description="开始时间（UTC）"),
    end: datetime | None = Query(None, description="结束时间（UTC）"),
    limit: int = Query(1000, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_read_db),
) -> dict:
    try:
        bars = market_service.get_kline(db, symbol, period, start, end, limit=limit, offset=offset)
    except ValueError as exc:
        raise ApiError(status_code=400, msg=str(exc)) from exc
    data = [KlineBarOut(**b).model_dump(mode="json") for b in bars]
    return ok(data=data)


@router.get("/kline/quality")
def get_kline_quality(
    symbol: str = Query(...),
    period: str = Query("1d", pattern="^(15m|1d|1w|1mon)$"),
    db: Session = Depends(get_read_db),
) -> dict:
    from app.services import kline_quality_service

    symbol_id = market_service.resolve_symbol_id(db, symbol)
    sym = db.get(Symbol, symbol_id) if symbol_id is not None else None
    if sym is None:
        raise ApiError(status_code=404, msg="标的不存在")
    if period != "1d" or not kline_quality_service.eligible(sym):
        return ok(data={"status": "unsupported", "missing_count": 0, "missing_ranges": [], "checked_at": None})
    return ok(data=kline_quality_service.quality_dict(kline_quality_service.get_quality(db, sym.id, period)))


@router.get("/snapshot")
def get_snapshot(
    symbols: str = Query(..., description="逗号分隔的 symbol_id 列表"),
    db: Session = Depends(get_read_db),
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
    db: Session = Depends(get_read_db),
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
    fixed = sync_service.run_fixed_indices_sync(skip_existing=False)
    realtime = sync_service.run_realtime_poll()
    return ok(data={"fixed_indices": fixed, "realtime": realtime}, msg="全量同步完成")
