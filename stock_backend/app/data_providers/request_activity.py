"""Best-effort, short-lived visibility into requests made by Celery market tasks."""

import json
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from uuid import uuid4

from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
_context: ContextVar[dict | None] = ContextVar("provider_request_context", default=None)
_INDEX = "ops:provider-requests:active"
_TTL = 120


@contextmanager
def kline_scope(symbol: str, period: str, start: datetime, end: datetime, asset_type: str):
    token = _context.set({"symbol": symbol, "period": period, "start": start.isoformat(),
                          "end": end.isoformat(), "asset_type": asset_type})
    try:
        yield
    finally:
        _context.reset(token)


@contextmanager
def realtime_scope(symbols, asset_type: str):
    token = _context.set({"asset_type": asset_type, "symbols": [
        {"code": item.code, "name": item.name} for item in symbols[:50]],
        "symbol_count": len(symbols)})
    try:
        yield
    finally:
        _context.reset(token)


class ActiveProviderRequest:
    def __init__(self, provider: str, fn, kwargs: dict) -> None:
        self.key = ""
        try:
            from celery import current_task

            request = getattr(current_task, "request", None)
            if request is None or not request.id:
                return
            task_name = current_task.name
        except Exception as exc:
            logger.debug("provider request activity context unavailable: %s", exc)
            return
        context = _context.get() or {}
        activity_id = str(uuid4())
        self.key = f"ops:provider-requests:{activity_id}"
        self.data = {
            "id": activity_id,
            "task_id": request.id,
            "task_name": task_name,
            "queue": (request.delivery_info or {}).get("routing_key", "sync"),
            "provider": provider,
            "interface": getattr(fn, "__name__", str(fn)),
            "symbol": context.get("symbol") or kwargs.get("symbol"),
            "symbols": context.get("symbols", []),
            "symbol_count": context.get("symbol_count"),
            "asset_type": context.get("asset_type"),
            "period": context.get("period"),
            "start": context.get("start"),
            "end": context.get("end"),
            "started_at": datetime.now(UTC).isoformat(),
        }

    def update(self, phase: str, attempt: int, attempts: int, retry_after: float | None = None) -> None:
        if not self.key:
            return
        self.data.update(phase=phase, attempt=attempt, attempts=attempts,
                         retry_after=retry_after, updated_at=datetime.now(UTC).isoformat())
        try:
            redis = get_redis_client()
            with redis.pipeline() as pipe:
                pipe.set(self.key, json.dumps(self.data, ensure_ascii=False), ex=_TTL)
                pipe.zremrangebyscore(_INDEX, "-inf", time.time())
                pipe.zadd(_INDEX, {self.key: time.time() + _TTL})
                pipe.execute()
        except Exception as exc:
            logger.debug("provider request activity update failed: %s", exc)

    def close(self) -> None:
        if not self.key:
            return
        try:
            redis = get_redis_client()
            with redis.pipeline() as pipe:
                pipe.delete(self.key)
                pipe.zrem(_INDEX, self.key)
                pipe.execute()
        except Exception as exc:
            logger.debug("provider request activity cleanup failed: %s", exc)


def list_active_requests() -> list[dict]:
    redis = get_redis_client()
    now = time.time()
    redis.zremrangebyscore(_INDEX, "-inf", now)
    keys = redis.zrange(_INDEX, 0, 99)
    if not keys:
        return []
    values = redis.mget(keys)
    records = [json.loads(value) for value in values if value]
    return sorted(records, key=lambda row: row["started_at"], reverse=True)
