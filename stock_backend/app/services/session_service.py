"""G19 会话服务：session CRUD + refresh 轮换 + 复用检测 + 批量吊销。"""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session as DBSession

from app.core.config import get_settings
from app.core.security import (
    blacklist_refresh_token,
    hash_refresh_token,
    is_refresh_token_blacklisted,
)
from app.models.session import UserSession

_settings = get_settings()


def create_session(
    db: DBSession,
    user_id: int,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> UserSession:
    """创建新会话（refresh token 哈希入库，明文不落盘）。"""
    token_hash = hash_refresh_token(refresh_token)
    now = datetime.now(UTC)
    expires_at = now + timedelta(days=_settings.REFRESH_TOKEN_EXPIRE_DAYS)
    session = UserSession(
        user_id=user_id,
        refresh_token_hash=token_hash,
        user_agent=user_agent[:2000] if user_agent else None,
        ip_address=ip_address,
        expires_at=expires_at,
    )
    db.add(session)
    db.flush()
    return session


def get_active_sessions(db: DBSession, user_id: int) -> list[UserSession]:
    """获取用户所有活跃会话（未过期 + 未吊销）。"""
    now = datetime.now(UTC)
    return (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
        )
        .order_by(UserSession.created_at.desc())
        .all()
    )


def find_session_by_token(db: DBSession, refresh_token: str) -> UserSession | None:
    """根据 refresh token 明文查找会话（哈希匹配）。"""
    token_hash = hash_refresh_token(refresh_token)
    return (
        db.query(UserSession)
        .filter(UserSession.refresh_token_hash == token_hash)
        .first()
    )


def revoke_session(db: DBSession, session: UserSession) -> None:
    """吊销单个会话。"""
    session.revoked_at = datetime.now(UTC)
    db.flush()


def revoke_all_user_sessions(db: DBSession, user_id: int) -> int:
    """吊销用户所有活跃会话（复用检测触发 / 改密时调用），返回吊销数量。"""
    now = datetime.now(UTC)
    count = (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
        )
        .update({"revoked_at": now}, synchronize_session="fetch")
    )
    db.flush()
    return count


def validate_refresh_token(
    db: DBSession, refresh_token: str
) -> tuple[UserSession | None, str]:
    """校验 refresh token：哈希匹配 + 未过期 + 未吊销 + 未在 Redis 黑名单。

    返回 (session, error_msg)：
    - (session, "") = 有效
    - (None, "已过期") = token 已过期
    - (None, "已吊销") = session 已被吊销
    - (None, "已轮换") = token 已被轮换（复用检测！）
    - (None, "无效") = 找不到对应 session
    """
    session = find_session_by_token(db, refresh_token)
    if session is None:
        return None, "无效"

    # 检查 Redis 黑名单必须最先（轮换时旧 token 入黑名单，是复用检测的唯一信号；
    # 若先查 revoked_at，轮换过的 token 会命中"已吊销"而永远走不到复用检测分支）
    token_hash = hash_refresh_token(refresh_token)
    if is_refresh_token_blacklisted(token_hash):
        return None, "已轮换"

    # 检查 session 是否已吊销（登出/踢出场景）
    if session.revoked_at is not None:
        return None, "已吊销"

    # 检查是否已过期
    now = datetime.now(UTC)
    if session.expires_at <= now:
        return None, "已过期"

    return session, ""


def rotate_refresh_token(
    db: DBSession,
    old_session: UserSession,
    new_refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> UserSession:
    """轮换 refresh token：旧 session 吊销 + 旧 hash 入 Redis 黑名单 + 创建新 session。"""
    # 计算旧 token 剩余有效期（用于 Redis 黑名单 TTL）
    now = datetime.now(UTC)
    remaining = int((old_session.expires_at - now).total_seconds())

    # 旧 hash 入 Redis 黑名单（防复用：如果有人拿旧 token 再来，is_refresh_token_blacklisted 返回 True）
    blacklist_refresh_token(old_session.refresh_token_hash, max(remaining, 60))

    # 吊销旧 session
    revoke_session(db, old_session)

    # 创建新 session
    return create_session(db, old_session.user_id, new_refresh_token, user_agent, ip_address)
