"""API 公共依赖：数据库会话、Redis 客户端、当前用户（G19 含黑名单检查）。

鉴权口径（G29 定稿）：
- HTTP 端点：**只认 Authorization: Bearer**，不读 Cookie。
  理由：① 浏览器 WS 无法带 header，但 WS 由 ws_market.py 自行读 Cookie 鉴权，
  不经本模块；② HTTP 侧若接受 Cookie 鉴权会引入 CSRF 面（第三方站点可诱导浏览器
  自动携带 Cookie 发起写操作）。Cookie 仅用于 WS 握手。
- 所有路径统一做 access token jti 黑名单检查（登出/踢出即时失效）。
"""

from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import decode_access_token_full, is_access_token_blacklisted
from app.models.user import User
from app.repositories import user_repo
from app.utils.db import SessionLocal
from app.utils.redis_client import get_redis_client

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


def _resolve_user_id(token: str) -> int | None:
    """解析 access token → user_id；JWT 无效或 jti 已入黑名单返回 None。"""
    payload = decode_access_token_full(token)
    if payload is None:
        return None
    jti = payload.get("jti")
    if jti and is_access_token_blacklisted(jti):
        return None
    user_id = int(payload.get("sub", 0))
    return user_id or None


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """当前用户依赖：解析 Bearer JWT → 黑名单检查 → 返回 User；失败抛 401。"""
    if credentials is None or not credentials.credentials:
        raise ApiError(status_code=401, code=40100, msg="未登录")
    user_id = _resolve_user_id(credentials.credentials)
    if user_id is None:
        raise ApiError(status_code=401, code=40100, msg="登录已过期或无效")
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(status_code=401, code=40100, msg="用户不存在")
    # G18：已注销账户的 access token 立即失效（无需遍历黑名单）
    if user.is_deleted:
        raise ApiError(status_code=401, code=40103, msg="账户已注销")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选鉴权：token 缺失/无效返回 None 而非 401（如 /snapshot 按关注集缓存的场景）。"""
    if credentials is None or not credentials.credentials:
        return None
    user_id = _resolve_user_id(credentials.credentials)
    if user_id is None:
        return None
    return user_repo.get_by_id(db, user_id)


def get_current_admin(current: User = Depends(get_current_user)) -> User:
    """管理员依赖：非 is_admin 用户抛 403（管理端点：Provider 健康、目录同步等）。"""
    if not current.is_admin:
        raise ApiError(status_code=403, code=40300, msg="需要管理员权限")
    return current
