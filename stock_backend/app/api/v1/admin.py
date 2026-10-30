"""管理员 API：行情 Provider 健康检查、全量标的目录同步（is_admin 鉴权）。"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin
from app.api.deps import get_read_db
from app.core.response import ok
from app.data_providers.factory import get_provider
from app.models.user import User
from app.worker.tasks.sync_tasks import catalog_sync

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class TrafficLimits(BaseModel):
    interval_seconds: int = Field(ge=1, le=60)
    daily_budget: int = Field(ge=100, le=100000)


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
    data['queues'] = {name: redis.llen(name) for name in ('sync', 'backtest', 'ai', 'backup')}
    data['sync_status'] = {}
    for scope in ('fixed_indices', 'catalog'):
        row = ops_repo.get_latest_sync_status(db, scope)
        data['sync_status'][scope] = {'status': row.status, 'message': row.message} if row else None
    return ok(data=data)


@router.put('/traffic/limits')
def update_traffic_limits(payload: TrafficLimits, current: User = Depends(get_current_admin)) -> dict:
    from app.data_providers.traffic import usage
    from app.utils.redis_client import get_redis_client

    redis = get_redis_client()
    redis.mset({'provider:limit:interval': payload.interval_seconds,
                'provider:limit:budget': payload.daily_budget})
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
