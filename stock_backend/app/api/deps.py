"""API 公共依赖：数据库会话、Redis 客户端。"""

from collections.abc import Generator

from redis import Redis
from sqlalchemy.orm import Session

from app.utils.db import SessionLocal
from app.utils.redis_client import get_redis_client


def get_db() -> Generator[Session, None, None]:
    """FastAPI 依赖：请求级数据库会话，请求结束自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis() -> Redis:
    return get_redis_client()
