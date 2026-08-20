"""行情更新发布（Celery worker → Redis pub/sub → API 进程 WS 推送）。

realtime_poll / 新K线写入后发布到 market:updates，API 进程的市场监听器订阅并分发到 WS 连接。
Redis 不可用静默跳过（不影响主同步链路）。
"""

import json
import logging

from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

_MARKET_CHANNEL = "market:updates"


def _publish(payload: dict) -> None:
    try:
        get_redis_client().publish(_MARKET_CHANNEL, json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:  # noqa: BLE001
        logger.warning("market update publish failed (skip)")


def publish_snapshot(symbol_id: int, data: dict) -> None:
    _publish({"symbol_id": symbol_id, "type": "snapshot", "data": data})


def publish_kline(symbol_id: int, period: str, bar: dict) -> None:
    _publish({"symbol_id": symbol_id, "type": "kline", "period": period, "bar": bar})
