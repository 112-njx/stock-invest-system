"""应用配置：pydantic-settings 从环境变量 / .env 读取，禁止硬编码。

生产修改方式：复制 .env.example 为 .env 后按需调整。
"""

from functools import lru_cache
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ---- 基础 ----
    APP_NAME: str = "stock-backend"
    APP_ENV: str = "dev"  # dev / test / prod
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # ---- 数据库（PostgreSQL）----
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@127.0.0.1:5432/stock_invest"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 3600  # 秒

    # ---- Redis（缓存 + Celery 队列）----
    REDIS_URL: str = "redis://127.0.0.1:6379/0"
    SNAPSHOT_CACHE_TTL: int = 5  # 实时快照缓存秒数
    KLINE_CACHE_TTL: int = 300  # K线缓存秒数

    CELERY_BROKER_URL: str = "redis://127.0.0.1:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://127.0.0.1:6379/2"

    # ---- 行情同步 ----
    DATA_PROVIDER: str = "eastmoney"  # 行情源：eastmoney（可插拔扩展）
    KLINE_INIT_DAYS: int = 730  # 首次全量拉取天数（约2年）
    REALTIME_POLL_INTERVAL: int = 5  # 实时轮询间隔（秒）
    SYNC_INCREMENTAL_HOUR: int = 16  # 每日增量同步时刻（本地时区小时）
    SYNC_INCREMENTAL_MINUTE: int = 30
    SYNC_TIMEOUT: int = 30  # 数据源请求超时（秒）
    SYNC_RETRY_TIMES: int = 3  # 外部源重试次数
    SYNC_RETRY_BACKOFF: float = 2.0  # 退避基数（秒）
    SYNC_DAILY_LIST_TIMES: str = "16,17"  # 增量同步 beat cron 小时，逗号分隔

    # ---- DeepSeek（阶段三 LangChain 启用）----
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ---- 时区 ----
    TIMEZONE: str = "Asia/Shanghai"  # 展示用；DB 内一律存 UTC

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.TIMEZONE)


@lru_cache
def get_settings() -> Settings:
    return Settings()
