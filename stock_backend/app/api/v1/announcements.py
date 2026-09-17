"""系统公告 API：活跃公告查询（公开）+ 管理员发布（is_admin）+ 历史列表（G16 P1-8b）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin, get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.schemas.notification import AnnouncementIn
from app.services import notification_service

router = APIRouter(prefix="/api/v1", tags=["announcements"])


@router.get("/announcements/active")
def list_active_announcements(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
) -> dict:
    """当前活跃公告（is_active 且未过期），前端顶部 banner 数据源。公开免鉴权。"""
    rows = notification_service.list_active_announcements(db, limit=limit)
    return ok(data=[r.model_dump(mode="json") for r in rows])


@router.get("/announcements")
def list_announcements(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """全部公告（含历史/已停用），I 区「系统公告」入口查看。"""
    rows = notification_service.list_all_announcements(db, limit=limit, offset=offset)
    return ok(data=[r.model_dump(mode="json") for r in rows])


@router.post("/admin/announcements")
def publish_announcement(
    payload: AnnouncementIn,
    current: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> dict:
    """管理员发布系统公告（is_admin 鉴权）；可选向全部用户分发站内通知 + WS 广播。"""
    result = notification_service.publish_announcement(db, payload)
    return ok(data=result)
