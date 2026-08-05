"""Loguru-based logger factory with per-day rotating file sink."""

import sys
from pathlib import Path

from loguru import logger

from config.settings import get_settings

_INITIALIZED = False


def _init_sinks() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return

    s = get_settings()
    logger.remove()

    fmt = (
        "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <5} | "
        "{extra[request_id]:<28} | {extra[symbol]:<10} | "
        "{extra[stage]:<20} | {extra[latency_ms]:>6}ms | {message}"
    )

    logger.configure(extra={
        "request_id": "-",
        "symbol": "-",
        "stage": "-",
        "latency_ms": 0,
    })

    logger.add(sys.stderr, level=s.log_level, format=fmt, enqueue=False)
    logger.add(
        Path(s.log_dir) / "ingest_{time:YYYY-MM-DD}.log",
        level=s.log_level,
        format=fmt,
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
    )

    _INITIALIZED = True


def get_logger(name: str = "ingest"):
    _init_sinks()
    return logger.bind(component=name)
