"""通知服务：站内通知读写 + 系统公告发布/分发 + WS 推送。

WS 推送为 best-effort：用户离线时通知仍已落库，下次拉取列表即可见。
"""

import asyncio
import logging

from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.repositories import notification_repo
from app.schemas.notification import (
    AnnouncementIn,
    AnnouncementOut,
    NotificationListOut,
    NotificationOut,
)

logger = logging.getLogger(__name__)

# 通知类型
TYPE_SYSTEM = "system"
TYPE_BACKTEST_COMPLETE = "backtest_complete"
TYPE_AGENT_COMPLETE = "agent_complete"
TYPE_SECURITY = "security"


# ---------- WS 推送（best-effort）----------

def _push_ws(user_id: int, payload: dict) -> None:
    """向指定用户推送 WS 消息；无事件循环/无连接时静默跳过。"""
    try:
        from app.ws.manager import manager

        loop = manager.get_loop()
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(
            manager.send_to_user(user_id, {"type": "notification", "data": payload}),
            loop,
        )
    except Exception:  # noqa: BLE001
        logger.debug("push notification to user=%s skipped", user_id, exc_info=True)


def _broadcast_ws(message: dict) -> None:
    """向所有在线连接广播 WS 消息（系统公告）；无事件循环时静默跳过。"""
    try:
        from app.ws.manager import manager

        loop = manager.get_loop()
        if loop is None:
            return
        asyncio.run_coroutine_threadsafe(manager.broadcast_all(message), loop)
    except Exception:  # noqa: BLE001
        logger.debug("broadcast notification skipped", exc_info=True)


def _to_payload(row) -> dict:
    return NotificationOut.model_validate(row).model_dump(mode="json")


# ---------- 通知创建 ----------

def create_notification(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    content: str | None = None,
    push: bool = True,
) -> NotificationOut:
    """创建单条通知（写库 + best-effort WS 推送）。调用方负责 commit。"""
    row = notification_repo.create(db, user_id, type_, title, content)
    out = NotificationOut.model_validate(row)
    if push:
        _push_ws(user_id, out.model_dump(mode="json"))
    return out


def notify_backtest_complete(
    db: Session, user_id: int, task_id: int, symbol_name: str, status: str, summary: str | None = None
) -> NotificationOut:
    """回测任务完成通知（成功/失败）。"""
    if status == "success":
        title = f"回测完成：{symbol_name}"
        content = summary or f"回测任务 #{task_id} 已完成，点击查看结果。"
    else:
        title = f"回测失败：{symbol_name}"
        content = summary or f"回测任务 #{task_id} 执行失败，请检查策略或稍后重试。"
    return create_notification(db, user_id, TYPE_BACKTEST_COMPLETE, title, content)


def notify_agent_complete(
    db: Session, user_id: int, run_type: str, summary: str | None = None
) -> NotificationOut:
    """Agent 深度分析完成通知。"""
    title = "AI 深度分析完成"
    content = summary or f"您的 {run_type} 分析已完成，点击查看结论。"
    return create_notification(db, user_id, TYPE_AGENT_COMPLETE, title, content)


def notify_security(db: Session, user_id: int, title: str, content: str) -> NotificationOut:
    """安全类通知（密码修改/异常登录等）。"""
    return create_notification(db, user_id, TYPE_SECURITY, title, content)


# ---------- 通知查询/已读 ----------

def list_notifications(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> NotificationListOut:
    rows = notification_repo.list_for_user(db, user_id, limit=limit, offset=offset)
    return NotificationListOut(
        items=[NotificationOut.model_validate(r) for r in rows],
        total=notification_repo.count_for_user(db, user_id),
        unread=notification_repo.count_unread(db, user_id),
    )


def mark_read(db: Session, user_id: int, notification_id: int) -> NotificationOut:
    row = notification_repo.get_owned(db, user_id, notification_id)
    if row is None:
        raise ApiError(status_code=404, code=40410, msg="通知不存在")
    notification_repo.mark_read(db, row)
    db.commit()
    db.refresh(row)
    return NotificationOut.model_validate(row)


def mark_all_read(db: Session, user_id: int) -> int:
    count = notification_repo.mark_all_read(db, user_id)
    db.commit()
    return count


def unread_count(db: Session, user_id: int) -> int:
    return notification_repo.count_unread(db, user_id)


# ---------- 系统公告 ----------

def list_active_announcements(db: Session, limit: int = 10) -> list[AnnouncementOut]:
    rows = notification_repo.list_active_announcements(db, limit=limit)
    return [AnnouncementOut.model_validate(r) for r in rows]


def list_all_announcements(db: Session, limit: int = 50, offset: int = 0) -> list[AnnouncementOut]:
    rows = notification_repo.list_announcements(db, limit=limit, offset=offset)
    return [AnnouncementOut.model_validate(r) for r in rows]


def publish_announcement(db: Session, payload: AnnouncementIn) -> dict:
    """管理员发布公告；可选向全部用户分发站内通知（best-effort 全局 WS 广播）。"""
    row = notification_repo.create_announcement(
        db, payload.title, payload.content, payload.type, payload.expires_at
    )
    notified = 0
    if payload.notify_users:
        user_ids = notification_repo.list_all_user_ids(db)
        notified = notification_repo.create_many(
            db, user_ids, TYPE_SYSTEM, f"系统公告：{payload.title}", payload.content
        )
    db.commit()
    db.refresh(row)

    out = AnnouncementOut.model_validate(row)
    # 广播在 commit 之后（保证客户端收到时数据已可见）
    if notified:
        _broadcast_ws(
            {
                "type": "notification",
                "data": {
                    "id": 0,
                    "type": TYPE_SYSTEM,
                    "title": f"系统公告：{payload.title}",
                    "content": payload.content,
                    "is_read": False,
                    "created_at": out.created_at.isoformat(),
                    "read_at": None,
                },
            }
        )
    return {"announcement": out.model_dump(mode="json"), "notified_users": notified}
