"""行情缓存工具：K线 Redis 读写、缓存击穿锁、序列化。

供 market_service（查询缓存）与 sync_service（写入后失效/覆盖）复用，
Redis 不可用一律静默降级直查 PostgreSQL（不阻塞主链路）。
"""

import json
import logging
from datetime import UTC, datetime

from app.core.config import get_settings
from app.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)
settings = get_settings()


def as_utc(dt) -> datetime | None:
    """DB 返回的 naive 时间戳统一视为 UTC 并补时区（kline 列为 timestamp without time zone）。"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

SNAPSHOT_FIELDS = (
    "price",
    "change",
    "change_pct",
    "open",
    "high",
    "low",
    "pre_close",
    "volume",
    "amount",
    "turnover",
    "amplitude",
    "updated_at",
)


# ---- K线缓存 ----
def policy_revision():
    from app.services.market_policy import read
    return read()["revision"]


def kline_key(symbol_id: int, period: str, limit: int) -> str:
    return f"kline:{symbol_id}:{period}:{policy_revision()}:{limit}"


def get_kline_cache(symbol_id: int, period: str, limit: int) -> list | None:
    try:
        raw = get_redis_client().get(kline_key(symbol_id, period, limit))
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def set_kline_cache(symbol_id: int, period: str, limit: int, bars: list) -> None:
    try:
        get_redis_client().set(kline_key(symbol_id, period, limit), json.dumps(bars), ex=settings.KLINE_CACHE_TTL)
    except Exception:  # noqa: BLE001
        logger.warning("kline cache set failed: %s:%s:%s", symbol_id, period, limit)


def invalidate_kline_cache(symbol_id: int, period: str) -> None:
    """新 K 线写入后按 pattern 删除该标的所有周期缓存。"""
    try:
        r = get_redis_client()
        for key in r.scan_iter(match=f"kline:{symbol_id}:{period}:*"):
            r.delete(key)
    except Exception:  # noqa: BLE001
        logger.warning("kline cache invalidate failed: %s:%s", symbol_id, period)


def acquire_kline_lock(symbol_id: int, period: str, timeout: int = 5) -> bool:
    """缓存击穿保护：分布式锁 NX EX，仅一个请求回源 PG。Redis 不可用返回 True 放行。"""
    try:
        return bool(get_redis_client().set(f"kline_lock:{symbol_id}:{period}", "1", nx=True, ex=timeout))
    except Exception:  # noqa: BLE001
        return True


def release_kline_lock(symbol_id: int, period: str) -> None:
    try:
        get_redis_client().delete(f"kline_lock:{symbol_id}:{period}")
    except Exception:  # noqa: BLE001
        pass


def kline_bar_to_dict(bar) -> dict:
    return {
        "ts": bar.ts.isoformat(),
        "open": float(bar.open),
        "high": float(bar.high),
        "low": float(bar.low),
        "close": float(bar.close),
        "volume": int(bar.volume),
        "amount": float(bar.amount),
    }


# ---- 关注列表缓存 ----
def watchlist_key(user_id: int) -> str:
    return f"watchlist:{user_id}:{policy_revision()}"


def get_watchlist_cache(user_id: int) -> list | None:
    try:
        raw = get_redis_client().get(watchlist_key(user_id))
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def set_watchlist_cache(user_id: int, data: list) -> None:
    try:
        get_redis_client().set(watchlist_key(user_id), json.dumps(data), ex=settings.WATCHLIST_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass


def invalidate_watchlist_cache(user_id: int) -> None:
    """增删关注后清除 watchlist 缓存。"""
    try:
        r = get_redis_client()
        r.delete(watchlist_key(user_id))
    except Exception:  # noqa: BLE001
        pass


# ---- 搜索缓存 ----
def search_key(type_: str | None, keyword: str) -> str:
    return f"search:{type_ or 'all'}:{policy_revision()}:{keyword}"


def get_search_cache(type_: str | None, keyword: str) -> list | None:
    try:
        raw = get_redis_client().get(search_key(type_, keyword))
        return json.loads(raw) if raw else None
    except Exception:  # noqa: BLE001
        return None


def set_search_cache(type_: str | None, keyword: str, data: list) -> None:
    try:
        get_redis_client().set(search_key(type_, keyword), json.dumps(data), ex=settings.SEARCH_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass


def invalidate_search_cache() -> None:
    """目录同步完成后批量删除全部搜索缓存（search:*）。"""
    try:
        r = get_redis_client()
        for key in r.scan_iter(match="search:*"):
            r.delete(key)
    except Exception:  # noqa: BLE001
        pass


def _num(v):
    return float(v) if v is not None else None


def _iso(v):
    return v.isoformat() if v is not None else None
