"""Trigger the StockDB updater once a day in the configured local timezone."""

from celery.schedules import crontab


def build_beat_schedule() -> dict:
    return {
        "stockdb-update-daily": {
            "task": "app.worker.tasks.sync_tasks.update_stockdb_daily",
            "schedule": crontab(hour=16, minute=30),
            "options": {"expires": 3600},
        },
    }
