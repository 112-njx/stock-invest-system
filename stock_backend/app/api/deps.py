"""API 公共依赖：数据库会话、Redis 客户端、当前用户。"""

from collections.abc import Generator

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from redis import Redis
from sqlalchemy.orm import Session

from app.core.exceptions import ApiError
from app.core.security import decode_access_token
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


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """当前用户依赖：解析 Bearer JWT → 校验 → 返回 User；失败抛 401。"""
    if credentials is None:
        raise ApiError(status_code=401, code=40100, msg="未登录")
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise ApiError(status_code=401, code=40100, msg="登录已过期或无效")
    user = user_repo.get_by_id(db, user_id)
    if user is None:
        raise ApiError(status_code=401, code=40100, msg="用户不存在")
    return user


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User | None:
    """可选鉴权：token 缺失/无效返回 None 而非 401（如 /snapshot 按关注集缓存的场景）。"""
    if credentials is None:
        return None
    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        return None
    return user_repo.get_by_id(db, user_id)


def get_current_admin(current: User = Depends(get_current_user)) -> User:
    """管理员依赖：非 is_admin 用户抛 403（管理端点：Provider 健康、目录同步等）。"""
    if not current.is_admin:
        raise ApiError(status_code=403, code=40300, msg="需要管理员权限")
    return current
