"""结构化 JSON 日志：python-json-logger，自动附带 request-id。"""

import logging
import sys
from datetime import UTC, datetime

from pythonjsonlogger.json import JsonFormatter

from .request_id import get_request_id


class RequestIdJsonFormatter(JsonFormatter):
    """JSON 格式化器：统一输出字段并注入 request-id。"""

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record.setdefault("timestamp", datetime.now(UTC).isoformat())
        req_id = get_request_id()
        if req_id:
            log_record["request_id"] = req_id


def setup_logging(debug: bool = False) -> None:
    """配置根日志器：所有模块统一 JSON 结构化输出。"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(RequestIdJsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.DEBUG if debug else logging.INFO)
    # 收敛噪音日志
    for noisy in ("uvicorn.access", "watchfiles", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
