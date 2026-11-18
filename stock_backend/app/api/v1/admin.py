"""管理员 API：行情 Provider、队列与 worker 状态。"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.deps import get_db, get_read_db
from app.core.response import ok
from app.data_providers.factory import get_provider
from app.models.user import User
from app.models.symbol import Symbol
from app.worker.celery_app import celery_app
from app.worker.tasks.sync_tasks import catalog_sync

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)


@router.get('/local-market/update')
def get_local_update(current: User = Depends(get_current_admin)):
    from app.services.stockdb_update import status
    return ok(data=status())


@router.get('/local-market/update/events')
def local_update_events(task_id: str, after_seq: int = Query(0, ge=0), before_seq: int | None = Query(None, ge=1),
                        limit: int = Query(200, ge=1, le=500), current: User = Depends(get_current_admin)):
    from app.services.stockdb_update import events
    return ok(data=events(task_id, after_seq, before_seq, limit))


@router.post('/local-market/update')
def start_local_update(current: User = Depends(get_current_admin)):
    from app.services.stockdb_update import request_update
    return ok(data=request_update())
QUEUE_NAMES = ("fixed_indices", "backfill", "control", "sync", "backtest", "ai", "backup", "forecast_replay")


class MarketSourcePolicy(BaseModel):
    akshare_enabled: bool = False
    auto_update_enabled: bool = False


class IndicatorSettings(BaseModel):
    pandas_enabled: bool = False


@router.get('/indicator-settings')
def get_indicator_settings(current: User = Depends(get_current_admin)):
    from app.services import indicator_policy
    return ok(data=indicator_policy.read())


@router.put('/indicator-settings')
def update_indicator_settings(payload: IndicatorSettings, current: User = Depends(get_current_admin)):
    from app.services import indicator_policy
    return ok(data=indicator_policy.save(payload.pandas_enabled))


class MarketDisplaySettings(BaseModel):
    synthetic_wick_factor: float = Field(ge=0, le=1, allow_inf_nan=False)


@router.get('/market-display')
def get_market_display(current: User = Depends(get_current_admin)):
    from app.services import market_display
    return ok(data=market_display.read())


@router.put('/market-display')
def update_market_display(payload: MarketDisplaySettings, current: User = Depends(get_current_admin)):
    from app.services import market_display
    return ok(data=market_display.save(payload.synthetic_wick_factor))


@router.get('/market-source-policy')
def get_market_source_policy(current: User = Depends(get_current_admin)):
    from app.services import market_policy
    return ok(data=market_policy.read())


@router.put('/market-source-policy')
def update_market_source_policy(payload: MarketSourcePolicy, current: User = Depends(get_current_admin)):
    from app.services import market_policy
    from app.core.exceptions import ApiError
    try:
        return ok(data=market_policy.save(payload.akshare_enabled, payload.auto_update_enabled))
    except ValueError as exc:
        raise ApiError(status_code=400, msg=str(exc)) from exc


def _queue_name(task: dict) -> str | None:
    routing = (task.get("delivery_info") or {}).get("routing_key")
    if routing in QUEUE_NAMES:
        return routing
    return None


def _task_queue_state(redis) -> tuple[dict, dict]:
    queues = {name: {"ready": redis.llen(name), "active": 0, "delayed": 0, "reserved": 0} for name in QUEUE_NAMES}

    def inspect_one(name: str) -> dict:
        try:
            return getattr(celery_app.control.inspect(timeout=1), name)() or {}
        except Exception as exc:
            logger.warning("Celery inspect %s failed: %s", name, exc)
            return {}

    names = ("ping", "active_queues", "active", "scheduled", "reserved")
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        pings, active_queues, active, scheduled, reserved = pool.map(inspect_one, names)
    workers = {queue: any(node in pings and any(item.get("name") == queue for item in subscriptions)
                          for node, subscriptions in active_queues.items()) for queue in QUEUE_NAMES}
    for snapshot, field in ((active, "active"), (scheduled, "delayed"), (reserved, "reserved")):
        for tasks in snapshot.values():
            for item in tasks:
                task = item.get("request", item)
                queue = _queue_name(task)
                if queue is not None:
                    queues[queue][field] += 1
    return queues, workers


class TrafficLimits(BaseModel):
    interval_seconds: int = Field(ge=1, le=60)
    daily_budget: int = Field(ge=100, le=100000)
    retry_interval_seconds: int = Field(default=10, ge=1, le=120)


@router.get('/traffic')
def traffic_status(current: User = Depends(get_current_admin)) -> dict:
    from app.data_providers.traffic import usage
    from app.utils.redis_client import get_redis_client

    data = usage()
    from app.core.config import get_settings

    redis = get_redis_client()
    data['retry_interval_seconds'] = int(redis.get('provider:retry:interval') or get_settings().SYNC_RETRY_BACKOFF)
    return ok(data=data)


@router.get('/task-queues')
def task_queues(current: User = Depends(get_current_admin)) -> dict:
    from app.utils.redis_client import get_redis_client

    queues, workers = _task_queue_state(get_redis_client())
    return ok(data={"queues": queues, "workers": workers,
                    "observed_at": datetime.now(UTC).isoformat()})


@router.get('/local-services')
def local_services(current: User = Depends(get_current_admin)) -> dict:
    from app.services.admin_services import local_service_status

    return ok(data=local_service_status())


@router.get('/provider-requests')
def active_provider_requests(current: User = Depends(get_current_admin),
                             db: Session = Depends(get_read_db)) -> dict:
    from app.data_providers.request_activity import list_active_requests
    from app.services.sync_service import _provider_params

    records = list_active_requests()
    symbols = {row["symbol"] for row in records if row.get("symbol")}
    if symbols:
        matches = db.scalars(select(Symbol).where(Symbol.code.in_(symbols)))
        by_code = {(sym.code, _provider_params(sym)[1]): sym.name for sym in matches}
        for row in records:
            symbol = row.get("symbol")
            row["symbol_name"] = by_code.get((symbol, row.get("asset_type")), symbol)
    return ok(data={"requests": records, "observed_at": datetime.now(UTC).isoformat()})


@router.put('/traffic/limits')
def update_traffic_limits(payload: TrafficLimits, current: User = Depends(get_current_admin)) -> dict:
    from app.data_providers.traffic import usage
    from app.utils.redis_client import get_redis_client

    redis = get_redis_client()
    redis.mset({'provider:limit:interval': payload.interval_seconds,
                'provider:limit:budget': payload.daily_budget,
                'provider:retry:interval': payload.retry_interval_seconds})
    return ok(data=usage())


@router.get("/providers/health")
def providers_health(current: User = Depends(get_current_admin)) -> dict:
    """各行情 Provider 健康状态：可用/熔断中/失败次数/最近成功时间。"""
    return ok(data=get_provider().health())


@router.post("/catalog/sync")
def trigger_catalog_sync(current: User = Depends(get_current_admin)) -> dict:
    """手动触发全量标的目录同步，返回任务 ID（异步执行）。"""
    task = catalog_sync.delay()
    return ok(data={"task_id": task.id, "status": "queued"}, msg="目录同步已提交")
