"""鉴权服务：注册/登录/刷新/登出/会话管理（G19 双 token）+ 邮箱验证/密码重置/暴力保护（G23）。"""

import logging
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.security import (
    blacklist_access_token,
    create_access_token,
    decode_access_token_full,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.repositories import user_repo
from app.schemas.user import LoginIn, RegisterIn, UserOut
from app.services import email_token, session_service

logger = logging.getLogger(__name__)

# ---------- G23：登录暴力保护常量 ----------
_LOGIN_FAIL_MAX = 5  # 连续失败上限
_LOGIN_LOCK_SECONDS = 900  # 锁定 15 分钟


def _build_auth_result(
    db: Session, user, user_agent: str | None, ip_address: str | None
) -> dict:
    """签发双 token + 创建 session，返回 {token, refresh_token, user}。"""
    access_token = create_access_token(user.id)
    refresh_token = generate_refresh_token()
    session_service.create_session(db, user.id, refresh_token, user_agent, ip_address)
    db.commit()
    return {
        "token": access_token,
        "refresh_token": refresh_token,
        "user": UserOut.model_validate(user).model_dump(mode="json"),
    }


def register(
    db: Session,
    payload: RegisterIn,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    username = payload.username.strip()
    if user_repo.get_by_username(db, username):
        raise ApiError(status_code=400, code=40001, msg="用户名已被占用")
    # G23: 邮箱唯一性检查
    if user_repo.get_by_email(db, payload.email):
        raise ApiError(status_code=400, code=40002, msg="该邮箱已被注册")
    user = user_repo.create(db, username, hash_password(payload.password), payload.email, payload.nickname)
    db.refresh(user)
    result = _build_auth_result(db, user, user_agent, ip_address)
    # G23: 注册后发送验证邮件（best-effort，不阻断注册）
    _send_verify_email(db, user)
    return result


def login(
    db: Session,
    payload: LoginIn,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    username = payload.username.strip()
    # G23: 登录暴力保护 — 检查 Redis 计数器
    _check_login_lock(username)

    user = user_repo.get_by_username(db, username)
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_login_failure(username)
        raise ApiError(status_code=401, code=40101, msg="用户名或密码错误")

    # 登录成功：清零计数器
    _clear_login_failures(username)
    return _build_auth_result(db, user, user_agent, ip_address)


def refresh(
    db: Session,
    refresh_token: str,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> dict:
    """刷新 token：校验旧 refresh → 轮换签发新双 token → 返回 {token, refresh_token}。

    复用检测：如果旧 refresh 已在 Redis 黑名单（说明已被轮换过），则吊销该用户所有会话。
    """
    session, error = session_service.validate_refresh_token(db, refresh_token)

    if error == "已轮换":
        # 复用检测！有人拿已轮换的旧 token 再次请求 → 疑似被盗
        # 找到对应 session 的 user_id（通过 hash 查找，即使已吊销也能找到）
        from app.models.session import UserSession

        token_hash = hash_refresh_token(refresh_token)
        found = db.query(UserSession).filter(UserSession.refresh_token_hash == token_hash).first()
        if found:
            session_service.revoke_all_user_sessions(db, found.user_id)
        db.commit()
        raise ApiError(status_code=401, code=40102, msg="会话异常，所有设备已登出")

    if session is None:
        raise ApiError(status_code=401, code=40102, msg=f"刷新令牌{error}")

    # 轮换：旧 session 吊销 + 旧 hash 入黑名单 + 新 session
    new_refresh = generate_refresh_token()
    session_service.rotate_refresh_token(db, session, new_refresh, user_agent, ip_address)

    # 签发新 access token
    new_access = create_access_token(session.user_id)
    db.commit()

    return {
        "token": new_access,
        "refresh_token": new_refresh,
    }


def logout(db: Session, access_token: str, refresh_token: str | None = None) -> None:
    """登出：access token 入黑名单 + refresh session 吊销。"""
    # access token 入 Redis 黑名单
    payload = decode_access_token_full(access_token)
    if payload:
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            remaining = int(exp - datetime.now(UTC).timestamp())
            blacklist_access_token(jti, max(remaining, 0))

    # refresh session 吊销
    if refresh_token:
        session = session_service.find_session_by_token(db, refresh_token)
        if session and session.revoked_at is None:
            session_service.revoke_session(db, session)

    db.commit()


def get_sessions(db: Session, user_id: int, current_refresh_hash: str | None = None) -> list[dict]:
    """获取活跃设备列表，标记当前设备。"""
    sessions = session_service.get_active_sessions(db, user_id)
    result = []
    for s in sessions:
        result.append({
            "id": s.id,
            "user_agent": s.user_agent,
            "ip_address": s.ip_address,
            "created_at": s.created_at,
            "expires_at": s.expires_at,
            "is_current": current_refresh_hash and s.refresh_token_hash == current_refresh_hash,
        })
    return result


def revoke_session_by_id(db: Session, user_id: int, session_id: int) -> None:
    """踢出指定设备（吊销 session refresh，已签发 access 通过黑名单失效）。"""
    from app.models.session import UserSession

    session = (
        db.query(UserSession)
        .filter(UserSession.id == session_id, UserSession.user_id == user_id)
        .first()
    )
    if session is None:
        raise ApiError(status_code=404, code=40400, msg="会话不存在")

    # 将对应 refresh token hash 入 Redis 黑名单（确保轮换检测生效）
    now = datetime.now(UTC)
    remaining = int((session.expires_at - now).total_seconds())
    if remaining > 0:
        from app.core.security import blacklist_refresh_token
        blacklist_refresh_token(session.refresh_token_hash, remaining)

    session_service.revoke_session(db, session)
    db.commit()


# ==================================================================
# G23：邮箱验证 / 密码重置 / 登录暴力保护
# ==================================================================


def _frontend_base_url() -> str:
    """前端基地址：取 CORS_ORIGINS 第一个来源（用于拼装邮件中的跳转链接）。"""
    origins = get_settings().CORS_ORIGINS
    return origins.split(",")[0].strip() if origins else "http://localhost:5173"


def _send_verify_email(db: Session, user) -> None:
    """发送邮箱验证邮件（best-effort，失败只记日志不阻断）。"""
    if not user.email:
        return
    try:
        from app.services.email_service import send_email

        token = email_token.create_verify_token(user.id, user.email)
        verify_url = f"{_frontend_base_url()}/verify-email?token={token}"
        send_email(
            db=db,
            recipient=user.email,
            template_name="verify_email",
            context={"username": user.username, "verify_url": verify_url},
        )
    except Exception:  # noqa: BLE001
        logger.warning("send verify email failed for user=%s (best-effort)", user.username, exc_info=True)


def verify_email(db: Session, token: str) -> dict:
    """验证邮箱：校验 token → 标记 email_verified=True。"""
    result = email_token.verify_email_token(token)
    if result is None:
        raise ApiError(status_code=400, code=40010, msg="验证链接无效或已过期")
    user_id, email = result
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(status_code=404, code=40400, msg="用户不存在")
    if user.email != email:
        raise ApiError(status_code=400, code=40011, msg="邮箱不匹配")
    if user.email_verified:
        return {"message": "邮箱已验证，无需重复操作"}
    user_repo.set_email_verified(db, user)
    db.commit()
    return {"message": "邮箱验证成功"}


def forgot_password(db: Session, email: str) -> dict:
    """忘记密码：按邮箱发送重置链接（无论邮箱是否存在均返回成功，防枚举）。"""
    user = user_repo.get_by_email(db, email)
    if user is not None:
        try:
            from app.services.email_service import send_email

            token = email_token.create_reset_token(user.id, user.email)
            reset_url = f"{_frontend_base_url()}/reset-password?token={token}"
            send_email(
                db=db,
                recipient=user.email,
                template_name="password_reset",
                context={"username": user.username, "reset_url": reset_url},
            )
        except Exception:  # noqa: BLE001
            logger.warning("send reset email failed for %s (best-effort)", email, exc_info=True)
    # 无论是否存在，均返回相同响应（防邮箱枚举）
    return {"message": "如果该邮箱已注册，重置密码邮件已发送，请查收邮箱"}


def reset_password(db: Session, token: str, new_password: str) -> dict:
    """重置密码：校验 token → 更新密码 → 吊销所有 refresh token（G19 协调）。"""
    result = email_token.verify_reset_token(token)
    if result is None:
        raise ApiError(status_code=400, code=40012, msg="重置链接无效或已过期")
    user_id, email = result
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(status_code=404, code=40400, msg="用户不存在")
    if user.email != email:
        raise ApiError(status_code=400, code=40013, msg="邮箱不匹配")
    # 更新密码
    user_repo.update_password(db, user, hash_password(new_password))
    # 吊销该用户所有 refresh token（G19 会话吊销机制）
    session_service.revoke_all_user_sessions(db, user_id)
    db.commit()
    return {"message": "密码重置成功，请使用新密码登录"}


# ---------- G23：登录暴力保护（Redis 计数器）----------

def _get_redis_safe():
    """安全获取 Redis 客户端，不可用时返回 None。"""
    try:
        from app.utils.redis_client import get_redis_client
        return get_redis_client()
    except Exception:  # noqa: BLE001
        return None


def _check_login_lock(username: str) -> None:
    """检查用户是否被锁定（连续失败 ≥5 次 → 锁定 15min）。"""
    r = _get_redis_safe()
    if r is None:
        return  # Redis 不可用时降级放行
    try:
        key = f"login_fail:{username}"
        count = r.get(key)
        if count is not None and int(count) >= _LOGIN_FAIL_MAX:
            ttl = r.ttl(key)
            raise ApiError(
                status_code=423,
                code=42301,
                msg=f"登录失败次数过多，账户已锁定。请 {ttl // 60 + 1} 分钟后重试",
            )
    except ApiError:
        raise
    except Exception:  # noqa: BLE001
        pass  # Redis 不可用时降级放行


def _record_login_failure(username: str) -> None:
    """记录登录失败（Redis 计数器，首次设置 TTL 15min）。"""
    r = _get_redis_safe()
    if r is None:
        return
    try:
        key = f"login_fail:{username}"
        pipe = r.pipeline()
        pipe.incr(key)
        pipe.expire(key, _LOGIN_LOCK_SECONDS)
        pipe.execute()
        count = r.get(key)
        if count is not None and int(count) >= _LOGIN_FAIL_MAX:
            logger.warning("login locked: username=%s failures=%s", username, count)
    except Exception:  # noqa: BLE001
        pass  # Redis 不可用时 best-effort


def _clear_login_failures(username: str) -> None:
    """登录成功后清零失败计数。"""
    r = _get_redis_safe()
    if r is None:
        return
    try:
        r.delete(f"login_fail:{username}")
    except Exception:  # noqa: BLE001
        pass  # Redis 不可用时 best-effort
