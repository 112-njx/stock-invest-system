"""通知域读写：notifications / admin_announcements。

多租户隔离：通知查询强制带 user_id 过滤，防止越权读改他人通知。
"""

from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models.notification import AdminAnnouncement, Notification


# ---- notifications ----
def create(
    db: Session,
    user_id: int,
    type_: str,
    title: str,
    content: str | None = None,
) -> Notification:
    row = Notification(user_id=user_id, type=type_, title=title, content=content)
    db.add(row)
    db.flush()
    return row


def create_many(db: Session, user_ids: list[int], type_: str, title: str, content: str | None = None) -> int:
    """批量写入通知（系统公告分发用），返回写入条数。"""
    if not user_ids:
        return 0
    db.bulk_save_objects(
        [Notification(user_id=uid, type=type_, title=title, content=content) for uid in user_ids]
    )
    db.flush()
    return len(user_ids)


def list_for_user(db: Session, user_id: int, limit: int = 50, offset: int = 0) -> list[Notification]:
    """用户通知列表：未读优先，其次按时间倒序。"""
    stmt = (
        select(Notification)
        .where(Notification.user_id == user_id)
        .order_by(Notification.is_read.asc(), Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))


def count_for_user(db: Session, user_id: int) -> int:
    return db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == user_id)) or 0


def count_unread(db: Session, user_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        )
        or 0
    )


def get_owned(db: Session, user_id: int, notification_id: int) -> Notification | None:
    """按 id 取通知（强制 user_id 归属校验）。"""
    return db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user_id)
    )


def mark_read(db: Session, row: Notification) -> None:
    if not row.is_read:
        row.is_read = True
        row.read_at = datetime.now(UTC)
        db.flush()


def mark_all_read(db: Session, user_id: int) -> int:
    """全部标记已读，返回受影响行数。"""
    result = db.execute(
        update(Notification)
        .where(Notification.user_id == user_id, Notification.is_read.is_(False))
        .values(is_read=True, read_at=datetime.now(UTC))
    )
    db.flush()
    return result.rowcount or 0


def list_all_user_ids(db: Session) -> list[int]:
    """全部用户 id（系统公告分发用）。"""
    from app.models.user import User

    return [r[0] for r in db.execute(select(User.id))]


# ---- admin_announcements ----
def create_announcement(
    db: Session,
    title: str,
    content: str,
    type_: str = "info",
    expires_at: datetime | None = None,
) -> AdminAnnouncement:
    row = AdminAnnouncement(title=title, content=content, type=type_, expires_at=expires_at)
    db.add(row)
    db.flush()
    return row


def list_active_announcements(db: Session, limit: int = 10) -> list[AdminAnnouncement]:
    """当前活跃公告：is_active=true 且（无过期时间 或 未过期），按创建倒序。"""
    now = datetime.now(UTC)
    stmt = (
        select(AdminAnnouncement)
        .where(
            AdminAnnouncement.is_active.is_(True),
            (AdminAnnouncement.expires_at.is_(None)) | (AdminAnnouncement.expires_at > now),
        )
        .order_by(AdminAnnouncement.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def list_announcements(db: Session, limit: int = 50, offset: int = 0) -> list[AdminAnnouncement]:
    """全部公告（含历史/已停用），供 I 区「系统公告」入口查看。"""
    stmt = (
        select(AdminAnnouncement)
        .order_by(AdminAnnouncement.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(db.scalars(stmt))
