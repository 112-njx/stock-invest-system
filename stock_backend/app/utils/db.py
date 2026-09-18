"""SQLAlchemy 引擎与会话（G11 · P1-2b 读写分离）：连接池参数可配，时间统一 UTC。

路由策略（**显式**，而非 SQLAlchemy 透明 `binds`）
--------------------------------------------------
仓储层本就以 `db: Session` 为参数（`kline_repo.get_bars(db, ...)`），调用方决定用哪个会话。
因此读写分离只需提供「只读会话」并让纯行情读端点使用它，不必引入透明路由 ——
透明 binds 会把"同一事务里读写分裂到不同节点"的坑藏起来，事后极难排查。

- **读库**（`get_read_db` / `get_read_session`）：行情查询 / K线 / 快照 / 指标 / 目录搜索
  —— 高频、可容忍秒级复制延迟、不参与事务写。
- **主库**（`get_db` / `get_session`）：用户数据（关注 / 策略 / 会话 / 记忆）读写**一律走主库**
  —— 数据量小、一致性要求高，读己之写不能有延迟。

降级（本地开发必须有）
----------------------
`DATABASE_READ_URL` 为空时 `read_engine` **就是 `engine`**（同一对象），行为与未做读写分离
完全一致 —— 本地无从库也能跑，配置就绪即可上线。
"""

import logging

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)
_settings = get_settings()


def _engine_kwargs() -> dict:
    return {
        "pool_size": _settings.DB_POOL_SIZE,
        "max_overflow": _settings.DB_MAX_OVERFLOW,
        "pool_timeout": _settings.DB_POOL_TIMEOUT,
        "pool_recycle": _settings.DB_POOL_RECYCLE,
        # 取连接前探活：从库切换/重启后池里的旧连接会失效，pre_ping 是读写分离下的必需项
        "pool_pre_ping": True,
        "future": True,
    }


def build_engines(settings=None) -> tuple[Engine, Engine]:
    """按配置构造 ``(主库引擎, 读库引擎)``。

    抽成工厂函数是为了可测：读库是否启用取决于 `DATABASE_READ_URL`，而模块级引擎在 import
    时就固定了，测试无法在导入后改变配置。测试可直接用不同 settings 调用本函数断言路由决策。
    """
    s = settings or _settings
    primary = create_engine(s.DATABASE_URL, **_engine_kwargs())
    if s.DATABASE_READ_URL:
        return primary, create_engine(s.DATABASE_READ_URL, **_engine_kwargs())
    # 未配置从库 → **复用同一引擎对象**（单实例降级，读写行为零差异）
    return primary, primary


# 主库：一切写入 + 用户数据读写；读库：行情类只读（未配置时即上面的同一对象）
engine, read_engine = build_engines()
if read_engine is engine:
    logger.info("DATABASE_READ_URL not set, reads fall back to primary (single-instance degrade)")
else:
    logger.info("read-write splitting enabled: reads -> replica")

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
ReadSessionLocal = sessionmaker(bind=read_engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_session() -> Session:
    """主库会话（Celery 任务等非请求上下文使用，调用方负责关闭）。"""
    return SessionLocal()


def get_read_session() -> Session:
    """只读会话（Celery 任务/脚本中的行情读取用，调用方负责关闭）。"""
    return ReadSessionLocal()


def read_write_splitting_enabled() -> bool:
    """是否真正启用了读写分离（供监控/自检使用，勿用于业务分支）。"""
    return read_engine is not engine
