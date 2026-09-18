"""平台级指标采集：Celery 队列深度 / Redis 缓存命中率 / 行情新鲜度 / 回测积压（5.4）。

/metrics 端点每次 scrape 时调用 refresh_platform_metrics()，从 Redis/DB 采集后写入 Gauge；
DB/Redis 不可用时静默跳过不抛错（可观测不影响主流程）。
"""

import logging
from datetime import UTC, datetime

from app.utils.db import engine
from app.utils.market_cache import as_utc
from app.utils.redis_client import get_redis_client
from prometheus_client import Gauge
from sqlalchemy import text

logger = logging.getLogger(__name__)

QUEUE_DEPTH = Gauge("celery_queue_depth", "Celery 队列积压任务数", ["queue"])
CACHE_HIT_RATE = Gauge("redis_cache_hit_rate", "Redis 缓存命中率（0-1）")
MARKET_FRESHNESS = Gauge("market_data_freshness_seconds", "行情快照最新更新时间距现在的秒数")
BACKTEST_QUEUED = Gauge("backtest_queued_tasks", "回测队列 queued 任务数")

# G05（P1-1）备份监控：最近一次成功备份的年龄/大小、磁盘剩余、WAL 归档文件数
BACKUP_AGE = Gauge("backup_last_success_age_seconds", "最近一次成功备份距今秒数（-1 表示尚无成功备份）")
BACKUP_SIZE = Gauge("backup_last_dump_bytes", "最近一次全量备份文件大小（字节，-1 表示无）")
BACKUP_DISK_FREE = Gauge("backup_disk_free_ratio", "备份目录所在文件系统剩余空间占比（0-1）")
BACKUP_WAL_FILES = Gauge("backup_wal_archive_files", "WAL 归档目录文件数（-1 表示未配置/不可读）")

_CELERY_QUEUES = ("sync", "backtest", "ai", "backup")


def refresh_platform_metrics() -> None:
    """刷新全部平台级 Gauge（供 /metrics 端点调用）。"""
    _refresh_queue_depth()
    _refresh_cache_hit_rate()
    _refresh_market_freshness()
    _refresh_backtest_queued()
    _refresh_backup_metrics()


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
    """行情快照数据龄（秒）。

    G24（P1-3 时区统一）已决策跳过，`snapshot_realtime.updated_at` 仍为 naive
    （`timestamp without time zone`），**必须先 as_utc() 归一再与 aware 的 now 相减**，
    否则抛 `can't subtract offset-naive and offset-aware datetimes`。
    该异常曾被静默吞掉，且 Gauge 保留初始值 0.0 —— 指标显示"0 秒前"（最新），
    实为采集完全失败，`MarketDataStale` 告警永不触发，是典型的静默错误。
    """
    try:
        with engine.connect() as conn:
            row = conn.execute(text("SELECT max(updated_at) FROM snapshot_realtime")).scalar()
        if row is None:
            MARKET_FRESHNESS.set(float("nan"))  # 未同步行情
            return
        age = (datetime.now(UTC) - as_utc(row)).total_seconds()
        MARKET_FRESHNESS.set(max(age, 0.0))
    except Exception as e:  # noqa: BLE001
        # 置 NaN（Prometheus 的"未知"）而非保留旧值：采集失败必须可辨别，
        # 否则残留的上一次读数会被当成有效数据（本地开发库正是这样把 0.0 展示了很久）
        MARKET_FRESHNESS.set(float("nan"))
        logger.warning("market freshness collect failed: %s", e)


def _refresh_backtest_queued() -> None:
    try:
        with engine.connect() as conn:
            n = conn.execute(text("SELECT count(*) FROM backtest_tasks WHERE status='queued'")).scalar_one()
        BACKTEST_QUEUED.set(n)
    except Exception as e:  # noqa: BLE001
        logger.warning("backtest queued collect failed: %s", e)


def _refresh_backup_metrics() -> None:
    """备份状态（G05）：从 status.json 派生年龄/大小，实时探测磁盘剩余与 WAL 归档文件数。

    读不到时统一置 -1，告警规则据此判定「从未成功备份」；与其它 _refresh_* 一致，
    采集失败只告警不影响 /metrics 主流程。
    """
    from app.services import backup_service  # 惰性导入：避免模块加载时即创建备份目录

    try:
        status = backup_service.backup_status()
        age_hours = status.get("age_hours")
        BACKUP_AGE.set(float(age_hours) * 3600 if isinstance(age_hours, (int, float)) else -1.0)
        dump = status.get("steps", {}).get("pg_dump", {})
        BACKUP_SIZE.set(float(dump.get("size_bytes", -1)))
    except Exception as e:  # noqa: BLE001
        logger.warning("backup status collect failed: %s", e)
        BACKUP_AGE.set(-1.0)
        BACKUP_SIZE.set(-1.0)

    try:
        BACKUP_DISK_FREE.set(backup_service.disk_usage()["free_pct"] / 100)
    except Exception as e:  # noqa: BLE001
        logger.warning("backup disk collect failed: %s", e)
        BACKUP_DISK_FREE.set(-1.0)

    try:
        wal_files = backup_service.archive_status().get("wal_files")
        BACKUP_WAL_FILES.set(float(wal_files) if wal_files is not None else -1.0)
    except Exception as e:  # noqa: BLE001
        logger.warning("wal archive collect failed: %s", e)
        BACKUP_WAL_FILES.set(-1.0)
