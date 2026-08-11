"""平台级指标采集：Celery 队列深度 / Redis 缓存命中率 / 行情新鲜度 / 回测积压（5.4）。

/metrics 端点每次 scrape 时调用 refresh_platform_metrics()，从 Redis/DB 采集后写入 Gauge；
DB/Redis 不可用时静默跳过不抛错（可观测不影响主流程）。
"""

import logging
from datetime import UTC, datetime

from app.utils.db import engine
from app.utils.redis_client import get_redis_client
from prometheus_client import Gauge
from sqlalchemy import text

logger = logging.getLogger(__name__)

QUEUE_DEPTH = Gauge("celery_queue_depth", "Celery 队列积压任务数", ["queue"])
CACHE_HIT_RATE = Gauge("redis_cache_hit_rate", "Redis 缓存命中率（0-1）")
MARKET_FRESHNESS = Gauge("market_data_freshness_seconds", "行情快照最新更新时间距现在的秒数")
BACKTEST_QUEUED = Gauge("backtest_queued_tasks", "回测队列 queued 任务数")

_CELERY_QUEUES = ("sync", "backtest", "ai")


def refresh_platform_metrics() -> None:
    """刷新全部平台级 Gauge（供 /metrics 端点调用）。"""
    _refresh_queue_depth()
    _refresh_cache_hit_rate()
    _refresh_market_freshness()
    _refresh_backtest_queued()


def _refresh_queue_depth() -> None:
    try:
        r = get_redis_client()
        for q in _CELERY_QUEUES:
            QUEUE_DEPTH.labels(q).set(r.llen(q))
    except Exception as e:  # noqa: BLE001
        logger.warning("queue depth collect failed: %s", e)


def _refresh_cache_hit_rate() -> None:
    try:
        info = get_redis_client().info("stats")
        hits = int(info.get("keyspace_hits", 0))
        misses = int(info.get("keyspace_misses", 0))
        total = hits + misses
        CACHE_HIT_RATE.set(hits / total if total else 0.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("cache hit rate collect failed: %s", e)


def _refresh_market_freshness() -> None:
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT max(updated_at) FROM snapshot_realtime")).scalar()
        if row is None:
            MARKET_FRESHNESS.set(float("nan"))  # 未同步行情
            return
        age = (datetime.now(UTC) - row).total_seconds()
        MARKET_FRESHNESS.set(max(age, 0.0))
    except Exception as e:  # noqa: BLE001
        logger.warning("market freshness collect failed: %s", e)


def _refresh_backtest_queued() -> None:
    try:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM backtest_tasks WHERE status='queued'")).scalar_one()
        BACKTEST_QUEUED.set(n)
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest queued collect failed: %s", e)
