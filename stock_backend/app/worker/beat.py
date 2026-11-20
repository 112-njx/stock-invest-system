"""Daily market jobs in the configured local timezone."""

from celery.schedules import crontab


def build_beat_schedule() -> dict:
    return {
        "headline-indices-daily": {
            "task": "app.worker.tasks.sync_tasks.refresh_headline_indices",
            "schedule": crontab(hour=16, minute=35, day_of_week="mon-fri"),
            "options": {"expires": 3600},
        },
        "stockdb-update-daily": {
            "task": "app.worker.tasks.sync_tasks.update_stockdb_daily",
            "schedule": crontab(hour=16, minute=30),
            "options": {"expires": 3600},
        },
    }
