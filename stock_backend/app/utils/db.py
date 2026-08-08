"""SQLAlchemy 引擎与会话：连接池参数可配，时间统一 UTC。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.DATABASE_URL,
    pool_size=_settings.DB_POOL_SIZE,
    max_overflow=_settings.DB_MAX_OVERFLOW,
    pool_timeout=_settings.DB_POOL_TIMEOUT,
    pool_recycle=_settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # 取连接前探活，避免拿到失效连接
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_session() -> Session:
    """获取独立会话（Celery 任务等非请求上下文使用，调用方负责关闭）。"""
    return SessionLocal()
