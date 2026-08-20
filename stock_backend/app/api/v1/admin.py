"""管理员 API：行情 Provider 健康检查、全量标的目录同步（is_admin 鉴权）。"""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_admin
from app.core.response import ok
from app.data_providers.factory import get_provider
from app.models.user import User
from app.worker.tasks.sync_tasks import catalog_sync

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/providers/health")
def providers_health(current: User = Depends(get_current_admin)) -> dict:
    """各行情 Provider 健康状态：可用/熔断中/失败次数/最近成功时间。"""
    return ok(data=get_provider().health())


@router.post("/catalog/sync")
def trigger_catalog_sync(current: User = Depends(get_current_admin)) -> dict:
    """手动触发全量标的目录同步，返回任务 ID（异步执行）。"""
    task = catalog_sync.delay()
    return ok(data={"task_id": task.id, "status": "queued"}, msg="目录同步已提交")
