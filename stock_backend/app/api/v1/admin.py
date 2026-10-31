"""管理员 API：行情 Provider、队列与 worker 状态。"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.deps import get_read_db
from app.core.response import ok
from app.data_providers.factory import get_provider
from app.models.user import User, UserWatchlist
from app.models.ops import SyncTask, TaskLog
from app.models.symbol import Symbol
from app.worker.celery_app import celery_app
from app.worker.tasks.sync_tasks import catalog_sync

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
logger = logging.getLogger(__name__)
QUEUE_NAMES = ("watchlist", "fixed_indices", "backfill", "control", "sync", "backtest", "ai", "backup")


def _queue_name(task: dict) -> str:
    name = task.get("name", "")
    if name.endswith("watchlist_stock_sync"):
        return "watchlist"
    if name.endswith("watchlist_delivery_reconcile"):
        return "control"
    if name.endswith("kline_init_fixed_indices"):
        return "fixed_indices"
    if name.endswith("kline_backfill"):
        return "backfill"
    for prefix, queue in (("backtest_tasks.", "backtest"), ("ai_tasks.", "ai"),
                          ("export_tasks.", "ai"), ("backup_tasks.", "backup")):
        if prefix in name:
            return queue
    return "sync"


def _task_queue_state(db: Session, redis) -> tuple[dict, dict]:
    queues = {name: {"ready": redis.llen(name), "active": 0, "delayed": 0,
                     "reserved": 0, "abnormal": 0} for name in QUEUE_NAMES}

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
                queues[_queue_name(task)][field] += 1
    queues["fixed_indices"]["abnormal"] = db.scalar(select(func.count()).select_from(SyncTask).join(
        Symbol, SyncTask.symbol_id == Symbol.id).where(
        SyncTask.status == "failed", Symbol.is_fixed_index.is_(True),
        SyncTask.task_type == "kline_init",
    )) or 0
    queues["watchlist"]["abnormal"] = db.scalar(select(func.count()).select_from(SyncTask).where(
        SyncTask.status == "failed", SyncTask.symbol_id.in_(select(UserWatchlist.symbol_id)),
        SyncTask.task_type.in_(("kline_init", "kline_incremental")),
    )) or 0
    queues["watchlist"]["delayed"] += db.scalar(select(func.count()).select_from(SyncTask).where(
        SyncTask.status.in_(("queued", "failed")), SyncTask.next_run_at > datetime.now(UTC),
        SyncTask.task_type.in_(("kline_init", "kline_incremental")),
        SyncTask.symbol_id.in_(select(UserWatchlist.symbol_id)),
    )) or 0
    queues["backfill"]["abnormal"] = db.scalar(select(func.count()).select_from(TaskLog).where(
        TaskLog.task_type == "kline_backfill", TaskLog.status == "failed",
        TaskLog.created_at >= datetime.now(UTC) - timedelta(hours=1),
    )) or 0
    return queues, workers


class TrafficLimits(BaseModel):
    interval_seconds: int = Field(ge=1, le=60)
    daily_budget: int = Field(ge=100, le=100000)
    retry_interval_seconds: int = Field(default=10, ge=1, le=120)


@router.get('/traffic')
def traffic_status(current: User = Depends(get_current_admin), db: Session = Depends(get_read_db)) -> dict:
    from app.data_providers.traffic import usage
    from app.repositories import ops_repo
    from app.utils.redis_client import get_redis_client

    data = usage()
    from app.core.config import get_settings

    data['poll_interval_seconds'] = get_settings().REALTIME_POLL_INTERVAL
    data['probe_interval_seconds'] = get_settings().PROVIDER_PROBE_INTERVAL
    redis = get_redis_client()
    data['retry_interval_seconds'] = int(redis.get('provider:retry:interval') or get_settings().SYNC_RETRY_BACKOFF)
    data['sync_status'] = {}
    for scope in ('fixed_indices', 'catalog'):
        row = ops_repo.get_latest_sync_status(db, scope)
        data['sync_status'][scope] = {'status': row.status, 'message': row.message} if row else None
    return ok(data=data)


@router.get('/task-queues')
def task_queues(current: User = Depends(get_current_admin), db: Session = Depends(get_read_db)) -> dict:
    from app.utils.redis_client import get_redis_client

    queues, workers = _task_queue_state(db, get_redis_client())
    return ok(data={"queues": queues, "workers": workers})


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
