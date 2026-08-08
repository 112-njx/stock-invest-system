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
    }
