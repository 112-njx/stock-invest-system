"""Application settings loaded from environment / .env file."""

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    akshare_timeout_seconds: int
    log_level: str
    log_dir: str

    @property
    def db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def db_url_safe(self) -> str:
        return (
            f"mysql+pymysql://{self.db_user}:***"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    log_dir = os.getenv("INGEST_LOG_DIR", "./logs")
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    return Settings(
        db_host=os.getenv("DB_HOST", "127.0.0.1"),
        db_port=int(os.getenv("DB_PORT", "3306")),
        db_name=os.getenv("DB_NAME", "invest_stock_system"),
        db_user=os.getenv("DB_USER", "root"),
        db_password=os.getenv("DB_PASSWORD", "123456"),
        akshare_timeout_seconds=int(os.getenv("AKSHARE_TIMEOUT_SECONDS", "30")),
        log_level=os.getenv("INGEST_LOG_LEVEL", "INFO").upper(),
        log_dir=log_dir,
    )


settings = get_settings()
