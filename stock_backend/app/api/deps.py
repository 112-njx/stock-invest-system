"""API 公共依赖：数据库会话、Redis 客户端、当前用户（G19 含黑名单检查）。"""

from collections.abc import Generator

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import ApiError
from app.core.security import decode_access_token_full, is_access_token_blacklisted
from app.models.user import User
from app.repositories import user_repo
from app.utils.db import SessionLocal
from app.utils.redis_client import get_redis_client

_settings = get_settings()
_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis() -> Redis:
    return get_redis_client()


def _extract_token(
    credentials: HTTPAuthorizationCredentials | None,
    request: Request,
) -> str | None:
    """从 Bearer header 或 Cookie 提取 access token（header 优先）。"""
    if credentials and credentials.credentials:
        return credentials.credentials
    # G19: 回退到 Cookie（为 G29 WS 握手 Cookie 鉴权预留）
    return request.cookies.get(_settings.ACCESS_TOKEN_COOKIE_NAME)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """当前用户依赖：解析 JWT → 黑名单检查 → 返回 User；失败抛 401。"""
    token = _extract_token(credentials, request)
    if token is None:
        raise ApiError(status_code=401, code=40100, msg="未登录")

    # 解析 JWT
    payload = decode_access_token_full(token)
    if payload is None:
        raise ApiError(status_code=401, code=40100, msg="登录已过期或无效")

    # G19: access token 黑名单检查（登出/踢出后 jti 入黑名单）
    jti = payload.get("jti")
    if jti and is_access_token_blacklisted(jti):
        raise ApiError(status_code=401, code=40100, msg="登录已失效，请重新登录")

    # 向后兼容：旧 token 无 jti 也放行（不强制 jti）
    user_id = int(payload.get("sub", 0))
    if not user_id:
        raise ApiError(status_code=401, code=40100, msg="登录已过期或无效")

    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(status_code=401, code=40100, msg="用户不存在")
    return user


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选鉴权：token 缺失/无效返回 None 而非 401（如 /snapshot 按关注集缓存的场景）。"""
    token = _extract_token(credentials, request)
    if token is None:
        return None
    payload = decode_access_token_full(token)
    if payload is None:
        return None
    jti = payload.get("jti")
    if jti and is_access_token_blacklisted(jti):
        return None
    user_id = int(payload.get("sub", 0))
    if not user_id:
        return None
    return user_repo.get_by_id(db, user_id)


def get_current_admin(current: User = Depends(get_current_user)) -> User:
    """管理员依赖：非 is_admin 用户抛 403（管理端点：Provider 健康、目录同步等）。"""
    if not current.is_admin:
        raise ApiError(status_code=403, code=40300, msg="需要管理员权限")
    return current
