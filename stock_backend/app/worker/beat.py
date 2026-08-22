"""Celery Beat 调度：增量同步（每日收盘后）+ 实时轮询（交易时段，任务内自判）。"""

from celery.schedules import crontab

from app.core.config import get_settings


def build_beat_schedule() -> dict:
    settings = get_settings()
    return {
        "kline-incremental-daily": {
            "task": "app.worker.tasks.sync_tasks.kline_incremental",
            "schedule": crontab(hour=settings.SYNC_INCREMENTAL_HOUR, minute=settings.SYNC_INCREMENTAL_MINUTE),
        },
        "realtime-poll": {
            "task": "app.worker.tasks.sync_tasks.realtime_poll",
            "schedule": settings.REALTIME_POLL_INTERVAL,  # 秒
        },
        "provider-probe": {
            "task": "app.worker.tasks.sync_tasks.provider_probe",
            "schedule": settings.PROVIDER_PROBE_INTERVAL,  # 秒：探测熔断中 Provider
        },
        "catalog-sync-daily": {
            "task": "app.worker.tasks.sync_tasks.catalog_sync",
            "schedule": crontab(hour=3, minute=0),  # 每日凌晨 3:00 全量目录同步
        },
        "memory-cleanup-daily": {
            "task": "app.worker.tasks.ai_tasks.memory_cleanup",
            "schedule": crontab(hour=4, minute=0),  # 每日凌晨 4:00 低重要性记忆清理（阶段六 6.2）
        },
    }
