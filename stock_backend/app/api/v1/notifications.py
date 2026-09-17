"""通知 API：站内通知列表/已读/未读数（G16 P1-8b）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.core.response import ok
from app.models.user import User
from app.services import notification_service

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("")
def list_notifications(
    limit: int = Query(50, ge=1, le=200, description="每页条数"),
    offset: int = Query(0, ge=0, description="偏移量"),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """通知列表（未读优先，其次时间倒序），含总数与未读数。"""
    result = notification_service.list_notifications(db, current.id, limit=limit, offset=offset)
    return ok(data=result.model_dump(mode="json"))


@router.get("/unread-count")
def unread_count(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """未读通知数（前端铃铛红点/计数轮询）。"""
    return ok(data={"unread": notification_service.unread_count(db, current.id)})


@router.patch("/read-all")
def mark_all_read(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """全部标记已读，返回受影响条数。"""
    count = notification_service.mark_all_read(db, current.id)
    return ok(data={"updated": count})


@router.patch("/{notification_id}/read")
def mark_read(
    notification_id: int,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """单条标记已读（仅本人通知，越权 404）。"""
    row = notification_service.mark_read(db, current.id, notification_id)
    return ok(data=row.model_dump(mode="json"))
